import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import aiohttp
from aiohttp import WSMsgType, web

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

import device_hub  # noqa: E402
from http_api import create_app  # noqa: E402
from job_queue import FRAME_SIZE  # noqa: E402
from test_http_api import (  # noqa: E402
    ADMIN_TOKEN,
    CLIENT_TOKEN,
    HOME_TOKEN,
    OFFICE_TOKEN,
    RENDERED,
    ServerTestCase,
)

TIMEOUT = 5


class HubTestCase(ServerTestCase):
    async def connect(self, token: str = HOME_TOKEN, headers: dict | None = None) -> aiohttp.ClientWebSocketResponse:
        ws = await self.client.ws_connect(
            "/device", headers={"Authorization": f"Bearer {token}", "X-Device-Version": "python/1", **(headers or {})}
        )
        self.addAsyncCleanup(ws.close)
        return ws

    async def receive_job(self, ws) -> tuple[dict, list[bytes], dict]:
        header = json.loads((await ws.receive(timeout=TIMEOUT)).data)
        self.assertEqual(header["type"], "job")
        frames = []
        while True:
            message = await ws.receive(timeout=TIMEOUT)
            if message.type == WSMsgType.TEXT:
                return header, frames, json.loads(message.data)
            self.assertEqual(message.type, WSMsgType.BINARY)
            frames.append(message.data)

    async def until(self, condition, timeout: float = TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                self.fail("condition not met in time")
            await asyncio.sleep(0.01)

    async def assertClosed(self, ws) -> int:
        """Skip what the server sent before it closed; fail if it never closes."""
        while True:
            message = await ws.receive(timeout=TIMEOUT)
            if message.type not in (WSMsgType.TEXT, WSMsgType.BINARY):
                self.assertIn(message.type, (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING))
                return ws.close_code

    def assertReleased(self, job_id: str, attempts: int = 1) -> None:
        job = self.queue.job(job_id)
        self.assertEqual((job.status, job.attempts), ("queued", attempts))
        self.assertEqual(job.events[-1].event, "released")
        self.assertEventsMatchStatus(job_id)


class ConnectionTest(HubTestCase):
    async def test_refuses_the_upgrade_without_a_printer_token(self):
        for name, headers in {
            "none": {},
            "wrong": {"Authorization": "Bearer not-a-printer-token-0000000000"},
            "admin": {"Authorization": f"Bearer {ADMIN_TOKEN}"},
            "client": {"Authorization": f"Bearer {CLIENT_TOKEN}"},
            "no scheme": {"Authorization": HOME_TOKEN},
            "spoofed address": {"Cf-Connecting-IP": "127.0.0.1"},
        }.items():
            with self.subTest(name):
                with self.assertRaises(aiohttp.WSServerHandshakeError) as caught:
                    await self.client.ws_connect("/device", headers=headers)
                self.assertEqual(caught.exception.status, 401)
        self.assertFalse(self.hub.online("home"))

    async def test_records_the_connection_through_the_tunnel(self):
        await self.connect(headers={"Cf-Connecting-IP": "203.0.113.7", "Cf-Ray": "8f1e2d3c4b5a6978-GRU"})
        state = self.queue.printer_state("home")
        self.assertEqual((state.address, state.route, state.client_version), ("203.0.113.7", "tunnel", "python/1"))
        self.assertAlmostEqual(state.connected_since, time.time(), delta=5)
        self.assertTrue(self.hub.online("home"))
        self.assertFalse(self.hub.online("office"))

    async def test_records_a_direct_connection_and_clears_it_on_disconnect(self):
        ws = await self.connect(headers={"X-Device-Version": "esp32/0.1 " + "x" * 5000})
        state = self.queue.printer_state("home")
        self.assertEqual((state.address, state.route), ("127.0.0.1", "direct"))
        self.assertEqual(len(state.client_version), device_hub.MAX_FIELD_LENGTH)
        await ws.close()
        await self.until(lambda: not self.hub.online("home"))
        state = self.queue.printer_state("home")
        self.assertEqual((state.connected_since, state.address), (None, None))
        self.assertIsNotNone(state.last_seen)

    async def test_a_second_connection_closes_the_first_with_4000_and_takes_over_its_job(self):
        job = self.add_job()
        first = await self.connect()
        await first.receive(timeout=TIMEOUT)  # the job header
        second = await self.connect()
        self.assertEqual(await self.assertClosed(first), device_hub.REPLACED_CLOSE_CODE)
        header, frames, end = await self.receive_job(second)
        self.assertEqual((header["id"], end), (job.id, {"type": "end", "id": job.id}))
        self.assertTrue(self.hub.online("home"))
        await second.send_json({"type": "printed", "id": job.id})
        await self.until(lambda: self.queue.job(job.id).status == "printed")
        self.assertEqual(self.queue.job(job.id).attempts, 2)
        self.assertEventsMatchStatus(job.id)

    async def test_startup_forgets_old_connections_and_releases_jobs_left_sending(self):
        job = self.add_job()
        self.queue.take("home")
        self.queue.update_printer_state("office", connected_since=1.0, address="198.51.100.4", latency_ms=40.0)
        app = create_app(self.config, self.queue)
        for startup in app.on_startup:
            await startup(app)
        self.assertReleased(job.id)
        state = self.queue.printer_state("office")
        self.assertEqual((state.connected_since, state.address, state.latency_ms), (None, None, 40.0))


class DeliveryTest(HubTestCase):
    async def test_sends_job_frames_and_end_then_confirms_on_printed(self):
        job = self.add_job()
        ws = await self.connect()
        header, frames, end = await self.receive_job(ws)
        self.assertEqual(header, {"type": "job", "id": job.id, "size": len(RENDERED.escpos), "frames": job.frames})
        self.assertGreater(len(frames), 1)
        self.assertTrue(all(len(frame) <= FRAME_SIZE for frame in frames))
        self.assertEqual(b"".join(frames), RENDERED.escpos)
        self.assertEqual(end, {"type": "end", "id": job.id})
        await self.until(lambda: self.queue.job(job.id).sent_at is not None)
        self.assertEqual(self.hub.current_job("home"), {"id": job.id, "frames_sent": job.frames, "frames": job.frames})

        await ws.send_json({"type": "printed", "id": job.id})
        await self.until(lambda: self.queue.job(job.id).status == "printed")
        self.assertIsNone(self.hub.current_job("home"))
        events = [event.event for event in self.queue.job(job.id).events]
        self.assertEqual(events, ["received", "rendered", "sending", "sent", "printed"])

    async def test_jobs_go_one_at_a_time_in_order_and_only_to_their_printer(self):
        first, other, second = self.add_job("home"), self.add_job("office"), self.add_job("home")
        ws = await self.connect()
        for job in (first, second):
            header, _, _ = await self.receive_job(ws)
            self.assertEqual(header["id"], job.id)
            await ws.send_json({"type": "printed", "id": job.id})
        await self.until(lambda: self.queue.job(second.id).status == "printed")
        self.assertEqual(self.queue.job(other.id).status, "queued")

    async def test_a_new_job_is_delivered_at_once_to_a_waiting_printer(self):
        ws = await self.connect()
        await asyncio.sleep(0.05)
        job = self.add_job()
        self.hub.notify("home")
        header, _, _ = await asyncio.wait_for(self.receive_job(ws), 1)
        self.assertEqual(header["id"], job.id)

    async def test_the_recheck_finds_a_job_without_a_notify(self):
        with mock.patch.object(device_hub, "RECHECK_INTERVAL", 0.1):
            ws = await self.connect()
            await asyncio.sleep(0.05)
            job = self.add_job()
            header, _, _ = await self.receive_job(ws)
        self.assertEqual(header["id"], job.id)

    async def test_an_expired_job_is_never_delivered(self):
        job = self.add_job(expires_in=0.05)
        await asyncio.sleep(0.1)
        ws = await self.connect()
        with self.assertRaises(asyncio.TimeoutError):
            await ws.receive(timeout=0.3)
        self.assertEqual(self.queue.job(job.id).status, "expired")
        self.assertEventsMatchStatus(job.id)

    async def test_disconnect_mid_job_releases_it(self):
        job = self.add_job()
        ws = await self.connect()
        await ws.receive(timeout=TIMEOUT)
        await ws.close()
        await self.until(lambda: self.queue.job(job.id).status == "queued")
        self.assertReleased(job.id)
        self.assertIsNone(self.hub.current_job("home"))

    async def test_no_reply_within_the_timeout_releases_the_job_and_closes(self):
        job = self.add_job()
        with mock.patch.object(device_hub, "REPLY_TIMEOUT", 0.2):
            ws = await self.connect()
            await self.receive_job(ws)
            await self.assertClosed(ws)
        await self.until(lambda: not self.hub.online("home"))
        self.assertReleased(job.id)
        self.assertIn("no reply within", self.queue.job(job.id).events[-1].detail)
        self.assertAlmostEqual(self.hub.paused_until("home"), time.time() + device_hub.ERROR_PAUSE_SECONDS, delta=5)

    async def test_a_cancelled_job_in_sending_is_not_confirmed(self):
        job = self.add_job()
        ws = await self.connect()
        await self.receive_job(ws)
        self.queue.cancel(job.id)
        await ws.send_json({"type": "printed", "id": job.id})
        await asyncio.sleep(0.1)
        self.assertEqual(self.queue.job(job.id).status, "cancelled")
        self.assertTrue(self.hub.online("home"))

    async def test_a_handshake_that_races_shutdown_takes_no_job(self):
        job = self.add_job()
        prepare = web.WebSocketResponse.prepare

        async def prepare_then_shut_down(ws, request):
            result = await prepare(ws, request)
            self.hub._closing = True
            return result

        with mock.patch.object(web.WebSocketResponse, "prepare", prepare_then_shut_down):
            ws = await self.connect()
        self.assertEqual(await self.assertClosed(ws), aiohttp.WSCloseCode.GOING_AWAY)
        self.assertEqual((self.queue.job(job.id).status, self.queue.job(job.id).attempts), ("queued", 0))
        self.assertFalse(self.hub.online("home"))

    async def test_server_shutdown_releases_the_job_in_flight(self):
        job = self.add_job()
        ws = await self.connect()
        await self.receive_job(ws)
        await self.client.server.close()
        self.assertReleased(job.id)
        self.assertEqual(self.queue.job(job.id).events[-1].detail, "server shutdown")
        self.assertIn(await self.assertClosed(ws), (aiohttp.WSCloseCode.GOING_AWAY, None))


class FakeClock:
    def __init__(self) -> None:
        self.now = time.monotonic()

    def __call__(self) -> float:
        return self.now


class ErrorPauseTest(HubTestCase):
    """After a device error, that printer waits ERROR_PAUSE_SECONDS on the hub clock before the next delivery."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.clock = FakeClock()
        self.hub.clock = self.clock

    async def assertNothingSent(self, ws, printer: str = "home") -> None:
        self.hub.notify(printer)
        with self.assertRaises(asyncio.TimeoutError):
            await ws.receive(timeout=0.2)

    async def fail_job(self, ws, job_id: str) -> None:
        header, _, _ = await self.receive_job(ws)
        self.assertEqual(header["id"], job_id)
        await ws.send_json({"type": "error", "id": job_id, "message": "printer took no data: out of paper?"})
        await self.until(lambda: self.hub.paused_until("home") is not None)

    async def advance_and_wake(self, seconds: float) -> None:
        self.clock.now += seconds
        self.hub.notify("home")

    async def test_each_error_pauses_only_that_printer_and_the_third_failed_attempt_fails_the_job(self):
        job = self.add_job("home")
        home, office = await self.connect(), await self.connect(OFFICE_TOKEN)
        await self.fail_job(home, job.id)
        released = [event for event in self.queue.job(job.id).events if event.event == "released"]
        self.assertEqual(released[0].detail, "device error: printer took no data: out of paper?")
        self.assertAlmostEqual(self.hub.paused_until("home"), time.time() + device_hub.ERROR_PAUSE_SECONDS, delta=1)
        await self.assertNothingSent(home)

        office_job = self.add_job("office")
        self.hub.notify("office")
        header, _, _ = await self.receive_job(office)
        self.assertEqual(header["id"], office_job.id)
        _, body = await self.call("GET", "/api/printers", self.bearer(ADMIN_TOKEN))
        paused = {printer["id"]: printer["paused_until"] for printer in body["printers"]}
        self.assertIsNone(paused["office"])
        self.assertAlmostEqual(paused["home"], time.time() + device_hub.ERROR_PAUSE_SECONDS, delta=1)

        await self.advance_and_wake(device_hub.ERROR_PAUSE_SECONDS - 1)
        await self.assertNothingSent(home)
        await self.advance_and_wake(2)
        await self.fail_job(home, job.id)
        self.assertEqual(self.queue.job(job.id).attempts, 2)
        await self.assertNothingSent(home)

        await self.advance_and_wake(device_hub.ERROR_PAUSE_SECONDS + 1)
        await self.fail_job(home, job.id)
        self.assertEqual((self.status(job.id), self.queue.job(job.id).attempts), ("failed", 3))
        self.assertEventsMatchStatus(job.id)

    async def test_a_reconnect_does_not_skip_the_pause(self):
        job = self.add_job()
        ws = await self.connect()
        await self.fail_job(ws, job.id)
        await ws.close()
        await self.until(lambda: not self.hub.online("home"))
        ws = await self.connect()
        await self.assertNothingSent(ws)
        await self.advance_and_wake(device_hub.ERROR_PAUSE_SECONDS + 1)
        header, _, _ = await self.receive_job(ws)
        self.assertEqual((header["id"], self.queue.job(job.id).attempts), (job.id, 2))

    async def test_a_job_that_expires_during_the_pause_is_expired_not_sent(self):
        job = self.add_job(expires_in=0.5)
        ws = await self.connect()
        await self.fail_job(ws, job.id)
        self.assertEqual(self.status(job.id), "queued")
        await asyncio.sleep(0.6)
        await self.advance_and_wake(device_hub.ERROR_PAUSE_SECONDS + 1)
        await self.assertNothingSent(ws)
        self.assertEqual((self.status(job.id), self.queue.job(job.id).attempts), ("expired", 1))
        self.assertEventsMatchStatus(job.id)

    def status(self, job_id: str) -> str:
        return self.queue.job(job_id).status


class HostileDeviceTest(HubTestCase):
    """Nothing a device sends may crash the hub; a bad message costs the job's attempt and the connection."""

    async def test_protocol_violations_release_the_job_close_the_connection_and_the_hub_keeps_serving(self):
        violations = {
            "malformed JSON": lambda ws, job: ws.send_str('{"type": "printed", "id": '),
            "JSON array": lambda ws, job: ws.send_str('["printed"]'),
            "deep nesting": lambda ws, job: ws.send_str("[" * 30_000 + "]" * 30_000),
            "unknown type": lambda ws, job: ws.send_json({"type": "reboot", "id": job.id}),
            "no type": lambda ws, job: ws.send_json({"id": job.id}),
            "wrong id": lambda ws, job: ws.send_json({"type": "printed", "id": "deadbeef"}),
            "unhashable id": lambda ws, job: ws.send_json({"type": "printed", "id": {"a": [1]}}),
            "binary": lambda ws, job: ws.send_bytes(b"\x1b@printed"),
            "oversized": lambda ws, job: ws.send_str(json.dumps({"type": "error", "id": job.id,
                                                                 "message": "x" * 100_000})),
        }
        for attempt, (name, violate) in enumerate(violations.items()):
            with self.subTest(name):
                job = self.add_job()
                ws = await self.connect()
                await self.receive_job(ws)
                await violate(ws, job)
                await self.assertClosed(ws)
                await self.until(lambda: not self.hub.online("home"))
                self.assertReleased(job.id)
                self.queue.cancel(job.id)
        self.assertIn("sent JSON nested too deeply", self.logs.text())
        ws = await self.connect()
        job = self.add_job()
        self.hub.notify("home")
        header, _, _ = await self.receive_job(ws)
        await ws.send_json({"type": "printed", "id": header["id"]})
        await self.until(lambda: self.queue.job(job.id).status == "printed")

    async def test_a_reply_before_the_end_releases_the_job_unconfirmed(self):
        job = self.add_job()
        held = asyncio.Event()

        async def hold_frames(ws, data, *args, **kwargs):
            await held.wait()

        with mock.patch.object(web.WebSocketResponse, "send_bytes", hold_frames):
            ws = await self.connect()
            header = json.loads((await ws.receive(timeout=TIMEOUT)).data)
            self.assertEqual(header["type"], "job")
            await ws.send_json({"type": "printed", "id": job.id})
            await self.assertClosed(ws)
        await self.until(lambda: not self.hub.online("home"))
        self.assertReleased(job.id)
        self.assertNotIn("printed", [event.event for event in self.queue.job(job.id).events])
        self.assertIn("before its end", self.logs.text())

    async def test_a_reply_outside_a_job_closes_the_connection(self):
        ws = await self.connect()
        await ws.send_json({"type": "printed", "id": "abcd1234"})
        await self.assertClosed(ws)

    async def test_odd_pongs_for_an_outstanding_ping_are_ignored_without_closing(self):
        with mock.patch.object(device_hub, "PING_INTERVAL", 0.2):
            ws = await self.connect()
            ping = json.loads((await ws.receive(timeout=TIMEOUT)).data)
            self.assertEqual(ping["type"], "ping")
            for t in (None, "now", str(ping["t"]), ping["t"] + 1, [ping["t"]], {"t": ping["t"]}, 1e308, True):
                await ws.send_json({"type": "pong", "t": t})
            await asyncio.sleep(0.05)
            self.assertIsNone(self.queue.printer_state("home").latency_ms)
            self.assertTrue(self.hub.online("home"))
            await ws.send_json({"type": "pong", "t": ping["t"]})
            await self.until(lambda: self.queue.printer_state("home").latency_ms is not None)

    async def test_a_silent_connection_is_closed(self):
        with mock.patch.object(device_hub, "RECEIVE_TIMEOUT", 0.2):
            ws = await self.connect()
            await self.assertClosed(ws)
        await self.until(lambda: not self.hub.online("home"))


class PingTest(HubTestCase):
    async def test_a_pong_records_latency_and_last_seen(self):
        with mock.patch.object(device_hub, "PING_INTERVAL", 0.05):
            ws = await self.connect()
            before = self.queue.printer_state("home").last_seen
            ping = json.loads((await ws.receive(timeout=TIMEOUT)).data)
            self.assertEqual(ping["type"], "ping")
            await asyncio.sleep(0.02)
            await ws.send_json({"type": "pong", "t": ping["t"]})
            await self.until(lambda: self.queue.printer_state("home").latency_ms is not None)
        state = self.queue.printer_state("home")
        self.assertGreaterEqual(state.latency_ms, 20)
        self.assertLess(state.latency_ms, 2000)
        self.assertGreater(state.last_seen, before)

    async def test_a_pong_for_an_older_ping_is_ignored(self):
        with mock.patch.object(device_hub, "PING_INTERVAL", 0.05):
            ws = await self.connect()
            first = json.loads((await ws.receive(timeout=TIMEOUT)).data)
            second = json.loads((await ws.receive(timeout=TIMEOUT)).data)
            self.assertNotEqual(first["t"], second["t"])
            await ws.send_json({"type": "pong", "t": first["t"]})
            await asyncio.sleep(0.02)
            self.assertIsNone(self.queue.printer_state("home").latency_ms)
            self.assertTrue(self.hub.online("home"))


class OfficeIsolationTest(HubTestCase):
    async def test_each_token_maps_to_its_own_printer(self):
        home_job, office_job = self.add_job("home"), self.add_job("office")
        office = await self.connect(OFFICE_TOKEN)
        header, _, _ = await self.receive_job(office)
        self.assertEqual(header["id"], office_job.id)
        self.assertTrue(self.hub.online("office"))
        self.assertFalse(self.hub.online("home"))
        self.assertEqual(self.queue.job(home_job.id).status, "queued")


if __name__ == "__main__":
    unittest.main()
