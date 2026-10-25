"""Device client: keeps a WebSocket open to the print server and prints the jobs it sends."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Protocol

import aiohttp
import usb.core
from escpos.exceptions import DeviceNotFoundError
from escpos.printer import Usb

from fake_printer import RASTER, decode
from printer import PRODUCT_ID, VENDOR_ID

CLIENT_VERSION = "python/1"
INITIAL_DELAY = 1.0
MAX_DELAY = 60.0
# Longer than one 20 s ping interval, so a server that pings and then crashes keeps backing off.
MIN_STABLE_SECONDS = 30.0
REPLACED_CLOSE_CODE = 4000
# The server pings every 20 s, so this much silence means a dead connection.
RECEIVE_TIMEOUT = 60.0
# Without a bound, aiohttp waits forever for the server's close frame, and stop() hangs.
CLOSE_TIMEOUT = 3.0
USB_WRITE_TIMEOUT_MS = 10_000

log = logging.getLogger("print_device")


class SinkError(Exception):
    """A printer write failed; the message goes to the server as the job's error."""


class Sink(Protocol):
    def start(self, job_id: str) -> None: ...
    def write(self, chunk: bytes) -> None: ...
    def finish(self) -> None: ...
    def abort(self) -> None: ...


class UsbSink:
    """Writes raw ESC/POS bytes to the USB printer. The device is open only during a job."""

    def __init__(self) -> None:
        self._printer: Usb | None = None

    def start(self, job_id: str) -> None:
        self.abort()
        printer = Usb(VENDOR_ID, PRODUCT_ID, timeout=USB_WRITE_TIMEOUT_MS)
        try:
            printer.open()
        except DeviceNotFoundError as error:
            detail = " ".join(str(error).split())
            raise SinkError(
                f"cannot open USB printer {VENDOR_ID:04x}:{PRODUCT_ID:04x}: is it plugged in and on? ({detail})"
            ) from error
        self._printer = printer

    def write(self, chunk: bytes) -> None:
        if self._printer is None:
            raise SinkError("USB printer is not open")
        try:
            self._printer._raw(chunk)
        except usb.core.USBTimeoutError as error:
            raise SinkError(
                f"printer took no data for {USB_WRITE_TIMEOUT_MS // 1000} s: out of paper or cover open?"
            ) from error
        except usb.core.USBError as error:
            raise SinkError(f"USB write failed: {error.strerror or error}") from error

    def finish(self) -> None:
        self.abort()

    def abort(self) -> None:
        if self._printer is not None:
            printer, self._printer = self._printer, None
            printer.close()


class FakeSink:
    """Saves each job as ``<out_dir>/<job_id>.bin``, and its raster as ``.png``, in place of printing."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self._buffer = bytearray()
        self._job_id: str | None = None

    def start(self, job_id: str) -> None:
        self._buffer = bytearray()
        self._job_id = job_id

    def write(self, chunk: bytes) -> None:
        self._buffer += chunk

    def finish(self) -> None:
        if self._job_id is None:
            raise SinkError("no job started")
        data = bytes(self._buffer)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / f"{self._job_id}.bin").write_bytes(data)
        if RASTER not in data:
            return
        try:
            page = decode(data)
        except ValueError as error:
            raise SinkError(f"fake printer cannot decode the job: {error}") from error
        page.save(self.out_dir / f"{self._job_id}.png")

    def abort(self) -> None:
        self._buffer = bytearray()
        self._job_id = None


class _Outcome(Enum):
    STABLE = auto()  # lasted MIN_STABLE_SECONDS: the backoff resets
    FAILED = auto()
    REPLACED = auto()


@dataclass
class _Job:
    id: str
    size: int
    received: int = 0
    error: str | None = None


def _job_id(data: dict) -> str:
    return str(data.get("id"))


def _message(error: BaseException) -> str:
    return str(error) or type(error).__name__


class DeviceClient:
    """Runs the device side of ``GET /device`` until ``stop()``. Nothing the server sends ends ``run()``."""

    def __init__(
        self,
        server_url: str,
        token: str,
        sink: Sink,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.server_url = server_url
        self._token = token
        self._sink = sink
        self._sleep = sleep
        self._random = random
        self._clock = clock
        self._stopping = False
        self._task: asyncio.Task | None = None
        self._job: _Job | None = None

    def stop(self) -> None:
        self._stopping = True
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def run(self) -> None:
        self._task = asyncio.current_task()
        try:
            async with aiohttp.ClientSession() as http:
                delay = INITIAL_DELAY
                while not self._stopping:
                    outcome = await self._connect_once(http)
                    if outcome is _Outcome.STABLE:
                        delay = INITIAL_DELAY
                    # Equal jitter: wait between half the delay and the full delay.
                    wait = delay * (1 - self._random() / 2)
                    log.info("reconnecting in %.1f s", wait)
                    await self._sleep(wait)
                    delay = min(delay * 2, MAX_DELAY)
        except asyncio.CancelledError:
            if not self._stopping:
                raise
            self._task.uncancel()
        log.info("stopped")

    async def _connect_once(self, http: aiohttp.ClientSession) -> _Outcome:
        headers = {"Authorization": f"Bearer {self._token}", "X-Device-Version": CLIENT_VERSION}
        try:
            ws = await http.ws_connect(
                self.server_url, headers=headers, timeout=aiohttp.ClientWSTimeout(ws_receive=RECEIVE_TIMEOUT)
            )
        except aiohttp.WSServerHandshakeError as error:
            if error.status == 401:
                log.error("server refused the printer token (401): check --token-file or PRINT_DEVICE_TOKEN")
            else:
                log.warning("server refused the connection: HTTP %s %s", error.status, error.message)
            return _Outcome.FAILED
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as error:
            log.warning("cannot reach %s: %s", self.server_url, _message(error))
            return _Outcome.FAILED
        except Exception:
            log.exception("cannot connect to %s", self.server_url)
            return _Outcome.FAILED

        log.info("connected to %s", self.server_url)
        connected_at = self._clock()
        try:
            await self._serve(ws)
        except asyncio.TimeoutError:
            log.warning("no message from the server for %.0f s", RECEIVE_TIMEOUT)
        except (aiohttp.ClientError, aiohttp.WebSocketError, OSError) as error:
            log.warning("connection failed: %s", _message(error))
        except Exception:
            log.exception("session failed")
        finally:
            if self._job is not None:
                log.warning("job %s dropped: the connection ended before its end", self._job.id)
                self._job = None
                # On stop, a cancelled to_thread sink call may still run; the exit releases the printer.
                if not self._stopping:
                    await self._abort()
            await self._close(ws)

        if ws.close_code == REPLACED_CLOSE_CODE:
            log.warning("server closed this connection (4000): another device connected with this printer's token")
            return _Outcome.REPLACED
        log.info("disconnected (close code %s)", ws.close_code)
        return _Outcome.STABLE if self._clock() - connected_at >= MIN_STABLE_SECONDS else _Outcome.FAILED

    async def _serve(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            message = await ws.receive()
            if message.type == aiohttp.WSMsgType.BINARY:
                if self._job is None:
                    log.warning("dropped a %d-byte frame that arrived outside a job", len(message.data))
                else:
                    await self._write(message.data)
            elif message.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(message.data)
                except (ValueError, RecursionError):
                    data = None
                if not isinstance(data, dict):
                    log.warning("dropped a text message that is not a JSON object: %.80r", message.data)
                    continue
                kind = data.get("type")
                if kind == "ping":
                    await ws.send_json({"type": "pong", "t": data.get("t")})
                elif kind == "job":
                    await self._start(ws, data)
                elif kind == "end":
                    await self._end(ws, _job_id(data))
                else:
                    log.warning("dropped a message of unknown type %.80r", kind)
            elif message.type == aiohttp.WSMsgType.ERROR:
                raise message.data
            else:
                return

    async def _start(self, ws: aiohttp.ClientWebSocketResponse, data: dict) -> None:
        job_id = _job_id(data)
        if self._job is not None:
            dropped, self._job = self._job, None
            log.warning("job %s dropped: job %s arrived before its end", dropped.id, job_id)
            await self._abort()
            await self._reply_error(ws, dropped.id, f"job {job_id} arrived before this job's end")
        size = data.get("size")
        self._job = _Job(id=job_id, size=size if isinstance(size, int) else -1)
        try:
            await asyncio.to_thread(self._sink.start, job_id)
        except Exception as error:
            self._job.error = _message(error)

    async def _write(self, chunk: bytes) -> None:
        job = self._job
        job.received += len(chunk)
        if job.error is not None:
            return
        try:
            await asyncio.to_thread(self._sink.write, chunk)
        except Exception as error:
            job.error = _message(error)

    async def _end(self, ws: aiohttp.ClientWebSocketResponse, job_id: str) -> None:
        job = self._job
        if job is None or job.id != job_id:
            await self._reply_error(ws, job_id, f"no job {job_id} in progress")
            return
        self._job = None
        error = job.error
        # A short job prints a cut-off image; never confirm it.
        if error is None and job.received != job.size:
            error = f"received {job.received} bytes, expected {job.size}"
        if error is None:
            try:
                await asyncio.to_thread(self._sink.finish)
            except Exception as finish_error:
                error = _message(finish_error)
        if error is not None:
            await self._abort()
            await self._reply_error(ws, job_id, error)
            return
        log.info("job %s printed (%d bytes)", job_id, job.received)
        await ws.send_json({"type": "printed", "id": job_id})

    async def _reply_error(self, ws: aiohttp.ClientWebSocketResponse, job_id: str, error: str) -> None:
        log.error("job %s failed: %s", job_id, error)
        await ws.send_json({"type": "error", "id": job_id, "message": error})

    async def _close(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        # On timeout the cancelled close() drops the TCP connection itself.
        try:
            async with asyncio.timeout(CLOSE_TIMEOUT):
                await ws.close()
        except TimeoutError:
            log.warning("server did not answer the close within %.0f s; dropped the connection", CLOSE_TIMEOUT)

    async def _abort(self) -> None:
        try:
            await asyncio.to_thread(self._sink.abort)
        except Exception:
            log.exception("printer cleanup failed")
