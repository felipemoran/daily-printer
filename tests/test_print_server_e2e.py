import asyncio
import base64
import io
import json
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, ImageChops

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

from access_auth import AccessVerifier  # noqa: E402
from http_api import HUB, create_app  # noqa: E402
from job_queue import JobQueue  # noqa: E402
from print_device import DeviceClient, FakeSink  # noqa: E402
from test_access_auth import AUDIENCE, TEAM  # noqa: E402
from test_http_api import (  # noqa: E402
    ADMIN_TOKEN,
    CLIENT_TOKEN,
    HOME_TOKEN,
    OFFICE_TOKEN,
    PHOTO,
    SAMPLE_PAYLOAD,
    ServerTestCase,
    write_config,
)

TIMEOUT = 30
SCRIPT = _TESTS.parent / "src" / "scripts" / "print_server.py"
TICKET = json.loads((_TESTS.parent / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))


class RecordingSink(FakeSink):
    """A fake printer that records each job and can hold ``finish`` until the test opens its gate."""

    def __init__(self, out_dir: Path) -> None:
        super().__init__(out_dir)
        self.started: list[str] = []
        self.printed: list[str] = []
        self.gate = threading.Event()
        self.gate.set()
        self.reached_finish = threading.Event()

    def start(self, job_id: str) -> None:
        super().start(job_id)
        self.started.append(job_id)

    def finish(self) -> None:
        job_id = self.started[-1]
        super().finish()
        self.printed.append(job_id)
        self.reached_finish.set()
        self.gate.wait(TIMEOUT)


async def _fast(seconds: float) -> None:
    await asyncio.sleep(0.05)


async def _parked(seconds: float) -> None:
    await asyncio.Event().wait()


class EndToEndTest(ServerTestCase):
    """The real app, real device clients with fake printers, and one event loop."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.queued: dict[str, bytes] = {}
        add = self.queue.add

        def recording_add(printer, data, **fields):
            job = add(printer, data, **fields)
            self.queued[job.id] = data
            return job

        self.queue.add = recording_add

    def start_device(self, token: str, name: str, sleep=_fast) -> tuple[DeviceClient, RecordingSink]:
        sink = RecordingSink(self.tmp / name)
        device = DeviceClient(str(self.client.make_url("/device")), token, sink, sleep=sleep)
        task = asyncio.create_task(device.run())

        async def stop() -> None:
            sink.gate.set()
            device.stop()
            await task

        self.addAsyncCleanup(stop)
        return device, sink

    async def until(self, condition, timeout: float = TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                self.fail("condition not met in time")
            await asyncio.sleep(0.02)

    async def submit(self, printer: str, **job) -> str:
        job = {"printer": printer, "kind": "image", "title": "Holiday photo",
               "image": base64.b64encode(PHOTO).decode(), **job}
        status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=job)
        self.assertEqual(status, 201, body)
        return body["id"]

    def status(self, job_id: str) -> str:
        return self.queue.job(job_id).status

    def assertPrintedExactly(self, job_id: str, sink: RecordingSink) -> None:
        """The device got the queued ESC/POS bytes, and its paper equals the stored PNG pixel for pixel."""
        self.assertEqual((sink.out_dir / f"{job_id}.bin").read_bytes(), self.queued[job_id])
        stored = Image.open(io.BytesIO(self.queue.png(job_id))).convert("L")
        paper = Image.open(sink.out_dir / f"{job_id}.png").convert("L")
        self.assertEqual(paper.size, stored.size)
        self.assertIsNone(ImageChops.difference(paper, stored).getbbox())

    def assertAllEventsMatchStatus(self) -> None:
        for job in self.queue.jobs():
            self.assertEventsMatchStatus(job.id)

    async def restart_server(self) -> None:
        port = self.client.server.port
        await self.client.server.close()
        self.queue.close()
        self.queue = JobQueue(self.config.database)
        self.addCleanup(self.queue.close)
        app = create_app(self.config, self.queue, verifier=AccessVerifier(TEAM, AUDIENCE, keys=self.certs))
        self.hub = app[HUB]
        self.client = TestClient(TestServer(app, port=port))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_image_and_receipt_jobs_print_on_two_printers_pixel_for_pixel(self):
        _, home = self.start_device(HOME_TOKEN, "home")
        _, office = self.start_device(OFFICE_TOKEN, "office")
        await self.until(lambda: self.hub.online("home") and self.hub.online("office"))

        image_id = await self.submit("home")
        receipt_id = await self.submit("office", kind="receipt", title="Today", payload=SAMPLE_PAYLOAD)
        await self.until(lambda: self.status(image_id) == self.status(receipt_id) == "printed")

        self.assertPrintedExactly(image_id, home)
        self.assertPrintedExactly(receipt_id, office)
        self.assertEqual((home.printed, office.printed), ([image_id], [receipt_id]))
        self.assertEqual((self.queue.job(image_id).attempts, self.queue.job(receipt_id).attempts), (1, 1))
        status, body = await self.call("GET", "/api/printers", self.bearer(ADMIN_TOKEN))
        self.assertEqual(status, 200)
        for printer in body["printers"]:
            self.assertEqual((printer["online"], printer["printed_today"], printer["queued"]), (True, 1, 0))
            self.assertEqual(printer["client_version"], "python/1")
        self.assertAllEventsMatchStatus()

    async def test_a_template_job_prints_pixel_for_pixel_and_a_bad_one_is_refused_with_422(self):
        _, home = self.start_device(HOME_TOKEN, "home")
        await self.until(lambda: self.hub.online("home"))

        job_id = await self.submit("home", kind="template", title="OPS-2481", payload=TICKET)
        await self.until(lambda: self.status(job_id) == "printed")
        self.assertPrintedExactly(job_id, home)
        self.assertEqual(self.queue.job(job_id).kind, "template")
        self.assertEqual(self.queue.job(job_id).width, 384)

        status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body={
            "printer": "home", "kind": "template", "payload": {**TICKET, "template": "nope"}})
        self.assertEqual(status, 422, body)
        self.assertIn('unknown template "nope"', str(body))
        self.assertEqual([job.id for job in self.queue.jobs()], [job_id])
        self.assertEqual(home.printed, [job_id])
        self.assertAllEventsMatchStatus()

    async def test_a_restart_mid_job_delivers_the_job_again_as_a_duplicate(self):
        _, home = self.start_device(HOME_TOKEN, "home")
        await self.until(lambda: self.hub.online("home"))
        home.gate.clear()
        job_id = await self.submit("home")
        await self.until(home.reached_finish.is_set)

        # The paper is out, but the server stops before the device can confirm it.
        await self.restart_server()
        self.assertEqual(self.status(job_id), "queued")
        home.gate.set()
        await self.until(lambda: self.status(job_id) == "printed")

        self.assertEqual(home.printed, [job_id, job_id])
        self.assertEqual(self.queue.job(job_id).attempts, 2)
        events = [event.event for event in self.queue.job(job_id).events]
        self.assertEqual(events, ["received", "rendered", "sending", "sent", "released", "sending", "sent", "printed"])
        self.assertPrintedExactly(job_id, home)
        self.assertAllEventsMatchStatus()

    async def test_a_job_for_an_offline_printer_waits_then_prints_on_connect(self):
        job_id = await self.submit("office")
        await asyncio.sleep(0.3)
        self.assertEqual((self.status(job_id), self.hub.online("office")), ("queued", False))

        _, office = self.start_device(OFFICE_TOKEN, "office")
        await self.until(lambda: self.status(job_id) == "printed")
        self.assertPrintedExactly(job_id, office)
        self.assertAllEventsMatchStatus()

    async def test_an_expired_job_is_never_delivered(self):
        expired_id = await self.submit("office", expires_in=1)
        await asyncio.sleep(1.1)
        _, office = self.start_device(OFFICE_TOKEN, "office")
        await self.until(lambda: self.hub.online("office"))
        fresh_id = await self.submit("office")
        await self.until(lambda: self.status(fresh_id) == "printed")

        self.assertEqual(self.status(expired_id), "expired")
        self.assertEqual(office.started, [fresh_id])
        self.assertFalse((office.out_dir / f"{expired_id}.bin").exists())
        self.assertAllEventsMatchStatus()

    async def test_a_third_device_with_the_same_token_takes_over_and_the_old_one_gets_4000(self):
        _, office = self.start_device(OFFICE_TOKEN, "office")
        _, old = self.start_device(HOME_TOKEN, "old-home", sleep=_parked)
        await self.until(lambda: self.hub.online("home") and self.hub.online("office"))
        _, new = self.start_device(HOME_TOKEN, "new-home")
        await self.until(lambda: "server closed this connection (4000)" in self.logs.text())

        job_id = await self.submit("home")
        await self.until(lambda: self.status(job_id) == "printed")
        self.assertEqual((new.printed, old.started, office.started), ([job_id], [], []))
        self.assertTrue(self.hub.online("home"))
        self.assertAllEventsMatchStatus()


class PrintServerScriptTest(unittest.TestCase):
    """The entry point as a process: clear startup errors and a clean stop on SIGTERM."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="print-server-script-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def config(self, port: int) -> Path:
        path = write_config(self.tmp)
        path.write_text(re.sub(r"port = \d+", f"port = {port}", path.read_text()))
        return path

    def free_port(self) -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def run_server(self, config: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--config", str(config)],
                              capture_output=True, text=True, timeout=TIMEOUT)

    def test_a_config_problem_prints_the_config_error_and_exits_2(self):
        config = self.config(self.free_port())
        config.chmod(0o644)
        result = self.run_server(config)
        self.assertEqual(result.returncode, 2)
        self.assertIn("chmod 600", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_port_in_use_is_reported_in_one_line_and_exits_1(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            result = self.run_server(self.config(taken.getsockname()[1]))
        self.assertEqual(result.returncode, 1)
        self.assertIn("is in use", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_serves_creates_the_database_directory_and_stops_cleanly_on_sigterm(self):
        port = self.free_port()
        server = subprocess.Popen([sys.executable, str(SCRIPT), "--config", str(self.config(port))],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: server.poll() is None and server.kill())
        deadline = time.monotonic() + TIMEOUT
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    self.fail(f"server did not start: {server.communicate()[1]}")
                time.sleep(0.1)
        server.send_signal(signal.SIGTERM)
        _, stderr = server.communicate(timeout=TIMEOUT)
        self.assertEqual(server.returncode, 0, stderr)
        self.assertIn("stopped", stderr)
        self.assertTrue((self.tmp / "data" / "queue.db").is_file())
        for token in re.findall(r'token = "([^"]+)"', (self.tmp / "server.toml").read_text()):
            self.assertNotIn(token, stderr)


if __name__ == "__main__":
    unittest.main()
