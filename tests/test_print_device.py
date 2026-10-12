import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import usb.core
from aiohttp import WSCloseCode, WSMsgType, web
from aiohttp.test_utils import TestServer
from escpos.exceptions import DeviceNotFoundError
from escpos.printer import Dummy
from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import print_device  # noqa: E402
from print_device import CLIENT_VERSION, MIN_STABLE_SECONDS, DeviceClient, FakeSink, SinkError, UsbSink  # noqa: E402
from printer import PRINT_WIDTH_DOTS  # noqa: E402

TOKEN = "printer-token-home"
FRAME = 4096


def _raster() -> tuple[Image.Image, bytes]:
    image = Image.new("1", (PRINT_WIDTH_DOTS, 600), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 120, 40), fill=0)
    for y in range(50, 600, 9):
        draw.line((y % PRINT_WIDTH_DOTS, y, PRINT_WIDTH_DOTS - 1, y), fill=0)
    printer = Dummy()
    printer.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS
    printer.hw("INIT")
    printer.image(image, center=False)
    printer.ln(3)
    return image, printer.output


IMAGE, RASTER = _raster()


def _frames(data: bytes) -> list[bytes]:
    return [data[i:i + FRAME] for i in range(0, len(data), FRAME)]


async def _send_job(ws, job_id: str, data: bytes, *, size: int | None = None, end: bool = True) -> None:
    frames = _frames(data)
    await ws.send_json({"type": "job", "id": job_id, "size": len(data) if size is None else size, "frames": len(frames)})
    for frame in frames:
        await ws.send_bytes(frame)
    if end:
        await ws.send_json({"type": "end", "id": job_id})



class RecordingSink:
    def __init__(self, fail_on_write: int | None = None, fail_on_start: bool = False) -> None:
        self.data = bytearray()
        self.calls: list[str] = []
        self.fail_on_write = fail_on_write
        self.fail_on_start = fail_on_start

    def start(self, job_id: str) -> None:
        self.calls.append(f"start {job_id}")
        self.data.clear()
        if self.fail_on_start:
            raise SinkError("cannot open USB printer 6868:0200")

    def write(self, chunk: bytes) -> None:
        self.calls.append("write")
        if self.fail_on_write is not None and self.calls.count("write") == self.fail_on_write:
            raise SinkError("printer is out of paper")
        self.data += chunk

    def finish(self) -> None:
        self.calls.append("finish")

    def abort(self) -> None:
        self.calls.append("abort")


class DeviceClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.handler = None
        self.attempts = 0
        self.headers = []
        self.delays: list[float] = []
        self.stop_after_sleeps: int | None = None
        self.now = 0.0
        self.done = asyncio.get_running_loop().create_future()

        async def device(request: web.Request):
            self.attempts += 1
            self.headers.append(dict(request.headers))
            return await self.handler(request, self.attempts)

        app = web.Application()
        app.router.add_get("/device", device)
        self.server = TestServer(app)
        await self.server.start_server()
        self.url = str(self.server.make_url("/device")).replace("http://", "ws://", 1)

    async def asyncTearDown(self):
        await self.server.close()

    def _client(self, sink, random=lambda: 0.0) -> DeviceClient:
        async def sleep(seconds: float) -> None:
            self.delays.append(seconds)
            if self.stop_after_sleeps is not None and len(self.delays) >= self.stop_after_sleeps:
                self.client.stop()
            await asyncio.sleep(0)

        self.client = DeviceClient(self.url, TOKEN, sink, sleep=sleep, random=random, clock=lambda: self.now)
        return self.client

    async def _run_until_done(self, sink):
        task = asyncio.create_task(self._client(sink).run())
        try:
            result = await asyncio.wait_for(self.done, 10)
        finally:
            self.client.stop()
            await asyncio.wait_for(task, 10)
        return result

    async def _run_until_stopped(self, sink, sleeps: int) -> None:
        self.stop_after_sleeps = sleeps
        await asyncio.wait_for(self._client(sink).run(), 10)

    async def _accept(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        return ws

    def _on_session(self, script, *, from_attempt: int = 1, before=None):
        """Attempts before ``from_attempt`` run ``before(ws)``; the next one's ``script(ws)`` result ends the test."""

        async def handler(request, attempt):
            ws = await self._accept(request)
            if attempt < from_attempt:
                await before(ws)
            else:
                self.done.set_result(await script(ws))
            return ws

        self.handler = handler

    async def _ping(self, ws, t=1):
        await ws.send_json({"type": "ping", "t": t})
        return await ws.receive_json()

    async def test_fake_sink_receives_every_byte_of_a_multi_frame_raster(self):
        self.assertGreater(len(_frames(RASTER)), 5)

        async def script(ws):
            await _send_job(ws, "job-1", RASTER)
            return await ws.receive_json()

        self._on_session(script)
        with tempfile.TemporaryDirectory() as tmp:
            reply = await self._run_until_done(FakeSink(Path(tmp)))
            self.assertEqual({"type": "printed", "id": "job-1"}, reply)
            self.assertEqual(RASTER, (Path(tmp) / "job-1.bin").read_bytes())
            printed = Image.open(Path(tmp) / "job-1.png")
            self.assertIsNone(ImageChops.difference(IMAGE.convert("L"), printed.convert("L")).getbbox())
        self.assertEqual(f"Bearer {TOKEN}", self.headers[0]["Authorization"])
        self.assertEqual(CLIENT_VERSION, self.headers[0]["X-Device-Version"])

    async def test_printed_is_sent_only_after_end(self):
        sink = RecordingSink()

        async def script(ws):
            await _send_job(ws, "job-2", RASTER, end=False)
            before_end = await self._ping(ws)
            finished_before_end = "finish" in sink.calls
            await ws.send_json({"type": "end", "id": "job-2"})
            return before_end, finished_before_end, await ws.receive_json()

        self._on_session(script)
        before_end, finished_before_end, after_end = await self._run_until_done(sink)
        self.assertEqual({"type": "pong", "t": 1}, before_end)
        self.assertFalse(finished_before_end)
        self.assertEqual({"type": "printed", "id": "job-2"}, after_end)
        self.assertEqual(RASTER, bytes(sink.data))

    async def test_sink_write_failure_is_reported_as_error_with_its_message(self):
        async def script(ws):
            await _send_job(ws, "job-3", RASTER)
            return await ws.receive_json()

        self._on_session(script)
        sink = RecordingSink(fail_on_write=2)
        with self.assertLogs("print_device", "ERROR") as logs:
            reply = await self._run_until_done(sink)
        self.assertEqual({"type": "error", "id": "job-3", "message": "printer is out of paper"}, reply)
        self.assertEqual(2, sink.calls.count("write"), "writes stop after the first failure")
        self.assertEqual("abort", sink.calls[-1])
        self.assertNotIn("finish", sink.calls)
        self.assertIn("job-3 failed", "\n".join(logs.output))

    async def test_sink_start_failure_is_reported_as_error_with_its_message(self):
        async def script(ws):
            await _send_job(ws, "job-9", RASTER)
            return await ws.receive_json()

        self._on_session(script)
        sink = RecordingSink(fail_on_start=True)
        reply = await self._run_until_done(sink)
        self.assertEqual({"type": "error", "id": "job-9", "message": "cannot open USB printer 6868:0200"}, reply)
        self.assertEqual(["start job-9", "abort"], sink.calls)

    async def _assert_size_mismatch_is_an_error(self, sent: bytes, declared: int):
        async def script(ws):
            await _send_job(ws, "job-4", sent, size=declared)
            return await ws.receive_json()

        self._on_session(script)
        with tempfile.TemporaryDirectory() as tmp:
            reply = await self._run_until_done(FakeSink(Path(tmp)))
            self.assertEqual([], list(Path(tmp).iterdir()), "an errored job leaves no fake print")
        expected = f"received {len(sent)} bytes, expected {declared}"
        self.assertEqual({"type": "error", "id": "job-4", "message": expected}, reply)

    async def test_missing_last_frame_is_an_error_never_printed(self):
        await self._assert_size_mismatch_is_an_error(RASTER[:-len(_frames(RASTER)[-1])], len(RASTER))

    async def test_more_bytes_than_declared_is_an_error_never_printed(self):
        await self._assert_size_mismatch_is_an_error(RASTER, len(RASTER) - 1)

    async def test_end_with_another_id_is_an_error_and_keeps_the_job(self):
        async def script(ws):
            await _send_job(ws, "job-a", RASTER, end=False)
            await ws.send_json({"type": "end", "id": "job-b"})
            wrong_end = await ws.receive_json()
            await ws.send_json({"type": "end", "id": "job-a"})
            return wrong_end, await ws.receive_json()

        self._on_session(script)
        sink = RecordingSink()
        wrong_end, right_end = await self._run_until_done(sink)
        self.assertEqual({"type": "error", "id": "job-b", "message": "no job job-b in progress"}, wrong_end)
        self.assertEqual({"type": "printed", "id": "job-a"}, right_end)
        self.assertEqual(RASTER, bytes(sink.data))

    async def test_second_job_before_end_drops_the_first_with_an_error(self):
        async def script(ws):
            await _send_job(ws, "job-a", RASTER[:FRAME * 2], size=len(RASTER), end=False)
            await _send_job(ws, "job-b", RASTER)
            return [await ws.receive_json(), await ws.receive_json()]

        self._on_session(script)
        sink = RecordingSink()
        with self.assertLogs("print_device", "WARNING") as logs:
            replies = await self._run_until_done(sink)
        self.assertEqual(
            [
                {"type": "error", "id": "job-a", "message": "job job-b arrived before this job's end"},
                {"type": "printed", "id": "job-b"},
            ],
            replies,
        )
        self.assertIn("job job-a dropped", "\n".join(logs.output))
        self.assertLess(sink.calls.index("abort"), sink.calls.index("start job-b"))
        self.assertEqual(RASTER, bytes(sink.data))

    async def test_binary_frame_outside_a_job_is_not_printed(self):
        async def script(ws):
            await ws.send_bytes(b"\x1b@stray bytes")
            await _send_job(ws, "job-c", RASTER)
            return await ws.receive_json()

        self._on_session(script)
        sink = RecordingSink()
        with self.assertLogs("print_device", "WARNING") as logs:
            reply = await self._run_until_done(sink)
        self.assertEqual({"type": "printed", "id": "job-c"}, reply)
        self.assertEqual(RASTER, bytes(sink.data))
        self.assertIn("outside a job", "\n".join(logs.output))

    async def test_text_that_is_not_a_json_object_is_dropped_and_the_session_survives(self):
        async def script(ws):
            for text in ("not json", "[" * 100_000, '["job"]'):
                await ws.send_str(text)
            return await self._ping(ws, 7)

        self._on_session(script)
        with self.assertLogs("print_device", "WARNING") as logs:
            reply = await self._run_until_done(RecordingSink())
        self.assertEqual({"type": "pong", "t": 7}, reply)
        self.assertEqual(1, self.attempts)
        self.assertEqual(3, "\n".join(logs.output).count("not a JSON object"))

    async def test_unknown_message_type_is_dropped_and_the_session_survives(self):
        async def script(ws):
            await ws.send_json({"type": "status", "id": "job-d"})
            return await self._ping(ws, 8)

        self._on_session(script)
        with self.assertLogs("print_device", "WARNING") as logs:
            reply = await self._run_until_done(RecordingSink())
        self.assertEqual({"type": "pong", "t": 8}, reply)
        self.assertEqual(1, self.attempts)
        self.assertIn("unknown type 'status'", "\n".join(logs.output))

    async def test_pong_echoes_the_ping_number(self):
        async def script(ws):
            return [await self._ping(ws, t) for t in (1760000000123, 0.5)]

        self._on_session(script)
        replies = await self._run_until_done(RecordingSink())
        self.assertEqual([{"type": "pong", "t": 1760000000123}, {"type": "pong", "t": 0.5}], replies)

    async def test_invalid_utf8_frame_ends_the_session_and_the_client_reconnects(self):
        async def before(ws):
            await ws.send_frame(b"\xff\xfe", WSMsgType.TEXT)
            await ws.receive()

        self._on_session(self._ping, from_attempt=2, before=before)
        with self.assertLogs("print_device", "WARNING") as logs:
            reply = await self._run_until_done(RecordingSink())
        self.assertEqual({"type": "pong", "t": 1}, reply)
        self.assertEqual(2, self.attempts)
        self.assertEqual([1.0], self.delays)
        self.assertIn("Invalid UTF-8", "\n".join(logs.output))

    async def test_silent_server_times_out_and_the_client_reconnects(self):
        async def before(ws):
            await self._ping(ws)
            await ws.receive()

        self._on_session(self._ping, from_attempt=2, before=before)
        with mock.patch.object(print_device, "RECEIVE_TIMEOUT", 0.2), self.assertLogs("print_device", "WARNING") as logs:
            reply = await self._run_until_done(RecordingSink())
        self.assertEqual({"type": "pong", "t": 1}, reply)
        self.assertEqual(2, self.attempts)
        self.assertIn("no message from the server", "\n".join(logs.output))

    async def test_dropped_mid_job_reconnects_with_delay_that_resets_after_a_stable_session(self):
        async def handler(request, attempt):
            if attempt <= 2:
                return web.Response(status=503)
            ws = await self._accept(request)
            if attempt == 3:
                await _send_job(ws, "job-5", RASTER[:FRAME * 2], size=len(RASTER), end=False)
                await self._ping(ws)
                self.now += MIN_STABLE_SECONDS
                await ws.close()
                return ws
            await _send_job(ws, "job-5", RASTER)
            self.done.set_result(await ws.receive_json())
            return ws

        self.handler = handler
        sink = RecordingSink()
        reply = await self._run_until_done(sink)
        self.assertEqual({"type": "printed", "id": "job-5"}, reply)
        self.assertEqual(RASTER, bytes(sink.data), "the resent job starts over in the sink")
        self.assertIn("abort", sink.calls, "the half-received job releases the printer")
        self.assertEqual(4, self.attempts)
        self.assertEqual([1.0, 2.0, 1.0], self.delays)

    async def test_session_shorter_than_thirty_seconds_keeps_the_delay_growing(self):
        async def handler(request, attempt):
            ws = await self._accept(request)
            await self._ping(ws)
            self.now += MIN_STABLE_SECONDS - 0.1
            await ws.close()
            return ws

        self.handler = handler
        await self._run_until_stopped(RecordingSink(), 4)
        self.assertEqual([1.0, 2.0, 4.0, 8.0], self.delays)

    async def test_backoff_caps_at_sixty_seconds_and_jitter_stays_within_half(self):
        async def handler(request, attempt):
            return web.Response(status=503)

        self.handler = handler
        self.stop_after_sleeps = 9
        await asyncio.wait_for(self._client(RecordingSink(), random=lambda: 0.999).run(), 10)
        expected = [base * (1 - 0.999 / 2) for base in (1, 2, 4, 8, 16, 32, 60, 60, 60)]
        self.assertEqual([round(d, 6) for d in expected], [round(d, 6) for d in self.delays])

    async def test_refused_token_is_logged_and_backs_off(self):
        async def handler(request, attempt):
            return web.Response(status=401)

        self.handler = handler
        with self.assertLogs("print_device", "ERROR") as logs:
            await self._run_until_stopped(RecordingSink(), 4)
        self.assertEqual([1.0, 2.0, 4.0, 8.0], self.delays)
        self.assertIn("refused the printer token (401)", "\n".join(logs.output))

    async def test_replaced_connection_backs_off_without_reset(self):
        async def handler(request, attempt):
            ws = await self._accept(request)
            await self._ping(ws)
            self.now += MIN_STABLE_SECONDS
            await ws.close(code=4000, message=b"replaced")
            return ws

        self.handler = handler
        with self.assertLogs("print_device", "WARNING") as logs:
            await self._run_until_stopped(RecordingSink(), 3)
        self.assertEqual([1.0, 2.0, 4.0], self.delays)
        self.assertIn("(4000)", "\n".join(logs.output))

    async def test_stop_during_a_session_closes_the_socket(self):
        closed = asyncio.get_running_loop().create_future()

        async def script(ws):
            await self._ping(ws)
            self.client.stop()
            closed.set_result((await ws.receive()).data)

        self._on_session(script)
        await self._run_until_done(RecordingSink())
        self.assertEqual(WSCloseCode.OK, await asyncio.wait_for(closed, 10))
        self.assertEqual([], self.delays)


class UsbSinkTest(unittest.TestCase):
    def test_missing_printer_is_a_clear_error(self):
        with mock.patch.object(print_device, "Usb") as usb_class:
            usb_class.return_value.open.side_effect = DeviceNotFoundError("Unable to open USB printer\nnot found")
            with self.assertRaisesRegex(SinkError, "cannot open USB printer 6868:0200: is it plugged in"):
                UsbSink().start("job-6")

    def test_write_errors_are_clear_and_abort_releases_the_device(self):
        cases = {
            "timeout": (usb.core.USBTimeoutError("Operation timed out"), "out of paper or cover open"),
            "other": (usb.core.USBError("Pipe error"), "USB write failed: Pipe error"),
        }
        for name, (raised, expected) in cases.items():
            with self.subTest(name), mock.patch.object(print_device, "Usb") as usb_class:
                device = usb_class.return_value
                device._raw.side_effect = [None, raised]
                sink = UsbSink()
                sink.start("job-7")
                sink.write(RASTER[:FRAME])
                with self.assertRaisesRegex(SinkError, expected):
                    sink.write(RASTER[FRAME:FRAME * 2])
                sink.abort()
                sink.abort()
                device.close.assert_called_once()

    def test_writes_go_to_the_printer_unchanged_and_finish_closes(self):
        with mock.patch.object(print_device, "Usb") as usb_class:
            device = usb_class.return_value
            sink = UsbSink()
            sink.start("job-8")
            for frame in _frames(RASTER):
                sink.write(frame)
            sink.finish()
        self.assertEqual(RASTER, b"".join(call.args[0] for call in device._raw.call_args_list))
        device.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
