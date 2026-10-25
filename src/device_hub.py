"""Device side of the print server: the ``GET /device`` WebSocket sessions and job delivery."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from aiohttp import WSCloseCode, WSMsgType, web

from job_queue import FRAME_SIZE, JobQueue, Status
from server_config import ServerConfig

PING_INTERVAL = 20.0
REPLY_TIMEOUT = 120.0
# After a device error or a reply timeout: an out-of-paper printer must not use all its attempts in seconds.
ERROR_PAUSE_SECONDS = 60.0
# Three missed pongs: the connection is dead even when TCP has not noticed.
RECEIVE_TIMEOUT = 60.0
# A missed notify or a job that expired while queued costs at most this delay.
RECHECK_INTERVAL = 30.0
CLOSE_TIMEOUT = 5.0
# Every device message is a small JSON object.
MAX_DEVICE_MESSAGE = 64 * 1024
REPLACED_CLOSE_CODE = 4000
MAX_FIELD_LENGTH = 200

log = logging.getLogger("device_hub")


def bearer_token(request: web.Request) -> str | None:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


def _clip(value: object) -> str:
    """A device- or proxy-supplied value, made safe to store and to log on one line."""
    text = str(value)[:MAX_FIELD_LENGTH]
    return "".join(char if char.isprintable() else "?" for char in text)


@dataclass
class _Delivery:
    job_id: str
    frames: int
    reply: asyncio.Future
    frames_sent: int = 0
    ended: bool = False


@dataclass(eq=False)
class _Session:
    printer: str
    ws: web.WebSocketResponse
    delivery: _Delivery | None = None
    ping_t: int | None = None
    ping_sent: float = 0.0
    tasks: list[asyncio.Task] = field(default_factory=list)


class _ProtocolError(Exception):
    """The device sent something outside the protocol; the connection closes."""


class DeviceHub:
    def __init__(self, config: ServerConfig, queue: JobQueue, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.queue = queue
        self.clock = clock
        self._paused_until: dict[str, float] = {}
        self._sessions: dict[str, _Session] = {}
        self._wakes: defaultdict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self._background: set[asyncio.Task] = set()
        self._closing = False

    def start(self) -> None:
        """Forget connections and deliveries left over from a previous run."""
        for printer_id in self.config.printers:
            self.queue.update_printer_state(printer_id, connected_since=None, address=None)
        self.queue.release_all()

    async def shutdown(self) -> None:
        self._closing = True
        sessions = list(self._sessions.values())
        for session in sessions:
            for task in session.tasks:
                task.cancel()
        await asyncio.gather(*(task for session in sessions for task in session.tasks), return_exceptions=True)
        await asyncio.gather(
            *(session.ws.close(code=WSCloseCode.GOING_AWAY, message=b"server shutdown") for session in sessions),
            return_exceptions=True,
        )

    def notify(self, printer: str) -> None:
        self._wakes[printer].set()

    def online(self, printer: str) -> bool:
        return printer in self._sessions

    def paused_until(self, printer: str) -> float | None:
        remaining = self._paused_until.get(printer, 0.0) - self.clock()
        return time.time() + remaining if remaining > 0 else None

    def current_job(self, printer: str) -> dict | None:
        session = self._sessions.get(printer)
        delivery = session.delivery if session else None
        if delivery is None:
            return None
        return {"id": delivery.job_id, "frames_sent": delivery.frames_sent, "frames": delivery.frames}

    async def handle(self, request: web.Request) -> web.StreamResponse:
        token = bearer_token(request)
        printer = self.config.printer_for_token(token) if token else None
        if printer is None:
            log.warning("device connection refused: %s printer token", "wrong" if token else "no")
            raise web.HTTPUnauthorized(reason="no valid printer token")
        if self._closing:
            raise web.HTTPServiceUnavailable(reason="server is shutting down")

        ws = web.WebSocketResponse(timeout=CLOSE_TIMEOUT, max_msg_size=MAX_DEVICE_MESSAGE)
        await ws.prepare(request)
        if self._closing:
            await ws.close(code=WSCloseCode.GOING_AWAY, message=b"server shutdown")
            return ws
        session = _Session(printer.id, ws)
        older = self._sessions.get(printer.id)
        self._sessions[printer.id] = session
        if older is not None:
            self._replace(older)

        now = time.time()
        address = _clip(request.headers.get("Cf-Connecting-IP") or request.remote or "unknown")
        route = "tunnel" if "Cf-Ray" in request.headers else "direct"
        version = _clip(request.headers.get("X-Device-Version", "unknown"))
        self._update_state(
            printer.id, connected_since=now, last_seen=now, address=address, route=route, client_version=version
        )
        log.info("printer %s connected from %s (%s, client %s)", printer.id, address, route, version)

        session.tasks = [
            asyncio.create_task(self._deliver_loop(session)),
            asyncio.create_task(self._ping_loop(session)),
        ]
        close_code = WSCloseCode.OK
        try:
            close_code = await self._read(session)
        except Exception:
            log.exception("printer %s: session failed", printer.id)
            close_code = WSCloseCode.INTERNAL_ERROR
        finally:
            for task in session.tasks:
                task.cancel()
            if self._sessions.get(printer.id) is session:
                del self._sessions[printer.id]
                if not self._closing:
                    self._update_state(printer.id, connected_since=None, address=None)
                log.info("printer %s disconnected", printer.id)
            else:
                log.info("printer %s: older connection closed", printer.id)
            await asyncio.gather(*session.tasks, return_exceptions=True)
            with contextlib.suppress(Exception):
                await ws.close(code=close_code)
        return ws

    def _replace(self, older: _Session) -> None:
        for task in older.tasks:
            task.cancel()
        closing = asyncio.create_task(
            older.ws.close(code=REPLACED_CLOSE_CODE, message=b"replaced by a newer connection")
        )
        self._background.add(closing)
        closing.add_done_callback(self._background.discard)
        log.warning("printer %s: a new connection replaces the older one", older.printer)

    async def _read(self, session: _Session) -> int:
        """Handle device messages until the connection ends. Returns the close code to send."""
        ws = session.ws
        while True:
            try:
                message = await ws.receive(timeout=RECEIVE_TIMEOUT)
            except asyncio.TimeoutError:
                log.warning("printer %s: no message for %.0f s; closing", session.printer, RECEIVE_TIMEOUT)
                return WSCloseCode.GOING_AWAY
            if message.type == WSMsgType.TEXT:
                try:
                    self._on_text(session, message.data)
                except _ProtocolError as error:
                    log.warning("printer %s: %s; closing", session.printer, error)
                    return WSCloseCode.POLICY_VIOLATION
            elif message.type == WSMsgType.BINARY:
                log.warning("printer %s: sent a %d-byte binary frame; closing", session.printer, len(message.data))
                return WSCloseCode.UNSUPPORTED_DATA
            else:
                if message.type == WSMsgType.ERROR:
                    log.warning("printer %s: connection error: %s", session.printer, _clip(message.data))
                return WSCloseCode.OK

    def _on_text(self, session: _Session, text: str) -> None:
        try:
            data = json.loads(text)
        except RecursionError:
            raise _ProtocolError("sent JSON nested too deeply") from None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise _ProtocolError(f"sent a text message that is not a JSON object: {_clip(text)[:80]!r}")
        kind = data.get("type")
        if kind == "pong":
            # Compared with ==, never used as a key: the device controls the value's type.
            if session.ping_t is None or data.get("t") != session.ping_t:
                log.warning("printer %s: pong for no outstanding ping", session.printer)
                return
            latency_ms = round((time.monotonic() - session.ping_sent) * 1000, 1)
            session.ping_t = None
            self._update_state(session.printer, latency_ms=latency_ms, last_seen=time.time())
        elif kind in ("printed", "error"):
            delivery = session.delivery
            job_id = data.get("id")
            if delivery is None or job_id != delivery.job_id or delivery.reply.done():
                raise _ProtocolError(f"sent {kind!r} for job {_clip(job_id)!r}, which is not awaiting a reply")
            if not delivery.ended:
                raise _ProtocolError(f"sent {kind!r} for job {_clip(job_id)!r} before its end")
            delivery.reply.set_result(data)
        else:
            raise _ProtocolError(f"sent a message of unknown type {_clip(kind)[:80]!r}")

    async def _deliver_loop(self, session: _Session) -> None:
        wake = self._wakes[session.printer]
        while True:
            wake.clear()
            paused = self._paused_until.get(session.printer, 0.0) - self.clock()
            if paused > 0:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(wake.wait(), min(paused, RECHECK_INTERVAL))
                continue
            try:
                job = self.queue.take(session.printer)
            except Exception:
                log.exception("printer %s: cannot take the next job", session.printer)
                job = None
            if job is None:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(wake.wait(), RECHECK_INTERVAL)
                continue
            if not await self._deliver(session, job):
                with contextlib.suppress(Exception):
                    await session.ws.close(code=WSCloseCode.GOING_AWAY)
                return

    async def _deliver(self, session: _Session, job) -> bool:
        """Send one job and wait for its reply. False when the connection must close."""
        ws = session.ws
        delivery = _Delivery(job.id, job.frames, asyncio.get_running_loop().create_future())
        session.delivery = delivery
        detail = "connection lost"
        confirmed = False
        log.info("job %s sending to %s (attempt %d, %d bytes)", job.id, session.printer, job.attempts, job.size_bytes)
        try:
            await ws.send_json({"type": "job", "id": job.id, "size": job.size_bytes, "frames": job.frames})
            for start in range(0, len(job.data), FRAME_SIZE):
                await ws.send_bytes(job.data[start:start + FRAME_SIZE])
                delivery.frames_sent += 1
            # Set before the send: the reply may arrive while the send waits for the buffer to drain.
            delivery.ended = True
            await ws.send_json({"type": "end", "id": job.id})
            self.queue.mark_sent(job.id)
            try:
                reply = await asyncio.wait_for(delivery.reply, REPLY_TIMEOUT)
            except asyncio.TimeoutError:
                detail = f"no reply within {REPLY_TIMEOUT:.0f} s"
                self._pause(session.printer)
                return False
            if reply["type"] == "printed":
                self.queue.confirm(job.id)
                confirmed = True
                log.info("job %s printed on %s", job.id, session.printer)
                return True
            detail = f"device error: {_clip(reply.get('message'))}"
            self._pause(session.printer)
            return True
        except Exception as error:
            if not isinstance(error, (ConnectionError, RuntimeError)):
                log.exception("job %s: delivery to %s failed", job.id, session.printer)
            return False
        finally:
            session.delivery = None
            if not confirmed:
                if self._closing:
                    detail = "server shutdown"
                self._release(job.id, detail)

    def _pause(self, printer: str) -> None:
        self._paused_until[printer] = self.clock() + ERROR_PAUSE_SECONDS
        log.warning("printer %s: delivery paused for %.0f s", printer, ERROR_PAUSE_SECONDS)

    def _release(self, job_id: str, detail: str) -> None:
        try:
            self.queue.release(job_id, detail=detail)
            job = self.queue.job(job_id)
        except Exception:
            log.exception("job %s: cannot release it", job_id)
            return
        if job is None:
            return
        log.info("job %s is %s after a failed delivery: %s", job_id, job.status.value, detail)
        if job.status == Status.QUEUED:
            self.notify(job.printer)

    def _update_state(self, printer: str, **fields: float | str | None) -> None:
        try:
            self.queue.update_printer_state(printer, **fields)
        except Exception:
            log.exception("printer %s: cannot update its state", printer)

    async def _ping_loop(self, session: _Session) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            session.ping_t = int(time.time() * 1000)
            session.ping_sent = time.monotonic()
            try:
                await session.ws.send_json({"type": "ping", "t": session.ping_t})
            except (ConnectionError, RuntimeError):
                return
