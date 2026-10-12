import contextlib
import http.server
import io
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from PIL import Image

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS.parent / "src" / "scripts"))

import simulate  # noqa: E402
from printer import PRINT_WIDTH_DOTS  # noqa: E402

SCRIPT = _TESTS.parent / "src" / "scripts" / "simulate.py"
RUN_TIMEOUT = 240
SUMMARY_LINE = re.compile(r"^\s+(\w+)\s+(receipt|image)\s+(\w+)\s+(\d+) x (\d+) dots\s+[\d.]+ cm\s+(\S+\.png)$", re.M)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class SimulateScriptTest(unittest.TestCase):
    """simulate.py as a process. Its temp dir lives under a fresh TMPDIR, so every child it starts names that dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="simulate-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self.kill_leftovers)

    def leftovers(self) -> dict[int, str]:
        listing = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True).stdout
        found = {}
        for line in listing.splitlines():
            pid, _, command = line.strip().partition(" ")
            if self.tmp in command and int(pid) != os.getpid():
                found[int(pid)] = command
        return found

    def kill_leftovers(self) -> None:
        for pid in self.leftovers():
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)

    def assertNoLeftovers(self) -> None:
        deadline = time.monotonic() + 5
        while (found := self.leftovers()) and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(found, {}, "processes outlived simulate.py")

    def start(self, *args: str) -> subprocess.Popen:
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), *args], env={**os.environ, "TMPDIR": self.tmp},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        def close() -> None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()

        self.addCleanup(close)
        return process

    def workdir(self) -> Path:
        (workdir,) = Path(self.tmp).glob("print-sim-*")
        return workdir

    def assertNoTokenIn(self, output: str) -> None:
        workdir = self.workdir()
        tokens = [path.read_text().strip() for path in workdir.glob("*-token")] + [
            path.read_text().strip() for path in workdir.glob("*.token")
        ]
        tokens += re.findall(r'token = "([^"]+)"', (workdir / "server.toml").read_text())
        self.assertEqual(len(set(tokens)), 4)
        for token in tokens:
            self.assertNotIn(token, output)

    def test_once_prints_a_receipt_and_an_image_on_two_fake_printers_and_leaves_no_process(self):
        process = self.start("--once", "--port", str(_free_port()))
        stdout, stderr = process.communicate(timeout=RUN_TIMEOUT)
        self.assertEqual(process.returncode, 0, stderr)

        jobs = {printer: rest for printer, *rest in SUMMARY_LINE.findall(stdout)}
        self.assertEqual(sorted(jobs), ["home", "work"], stdout)
        self.assertEqual([jobs["home"][0], jobs["work"][0]], ["receipt", "image"])
        paper = {}
        for printer, (kind, status, width, height, png) in jobs.items():
            self.assertEqual(status, "printed")
            with Image.open(png) as image:
                paper[printer] = image.size
            self.assertEqual(paper[printer], (int(width), int(height)), f"{kind} paper differs from the job size")
        image_width, image_height = simulate.IMAGE_SIZE
        self.assertEqual(paper["work"], (PRINT_WIDTH_DOTS, image_height * PRINT_WIDTH_DOTS // image_width))
        self.assertEqual(paper["home"][0], PRINT_WIDTH_DOTS)
        self.assertGreater(paper["home"][1], PRINT_WIDTH_DOTS, "the sample receipt is longer than it is wide")

        workdir = self.workdir()
        for secret in ("server.toml", "admin-token", "home.token", "work.token"):
            self.assertEqual(stat.S_IMODE((workdir / secret).stat().st_mode), 0o600, secret)
        self.assertNoTokenIn(stdout + stderr)
        self.assertNoLeftovers()

    def start_serving(self) -> tuple[subprocess.Popen, dict[int, str], Callable[[], str]]:
        """Start without --once and wait until both jobs printed. Returns the process, its children and its output."""
        process = self.start("--port", str(_free_port()))
        lines: list[str] = []
        ready = threading.Event()

        def read() -> None:
            for line in process.stdout:
                lines.append(line)
                if "Press Ctrl-C" in line:
                    ready.set()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        self.addCleanup(reader.join, 10)
        self.assertTrue(ready.wait(RUN_TIMEOUT), "".join(lines))
        running = self.leftovers()
        self.assertGreaterEqual(len(running), 3, "server and two devices should be running")

        def output() -> str:
            process.wait(timeout=60)
            reader.join(10)
            return "".join(lines) + process.stderr.read()

        return process, running, output

    def assertStopped(self, running: dict[int, str]) -> None:
        for pid in running:
            with self.assertRaises(ProcessLookupError, msg=f"pid {pid} still runs"):
                os.kill(pid, 0)
        self.assertNoLeftovers()

    def test_ctrl_c_while_running_stops_the_server_and_both_devices_and_exits_0(self):
        process, running, output = self.start_serving()
        process.send_signal(signal.SIGINT)
        text = output()
        self.assertEqual(process.returncode, 0, text)
        self.assertIn(f"Admin token:   {self.workdir() / 'admin-token'}", text)
        self.assertIn("printctl.py", text)
        self.assertNoTokenIn(text)
        self.assertStopped(running)

    def test_sigterm_while_running_stops_the_server_and_both_devices_and_exits_0(self):
        process, running, output = self.start_serving()
        process.send_signal(signal.SIGTERM)
        text = output()
        self.assertEqual(process.returncode, 0, text)
        self.assertNoTokenIn(text)
        self.assertStopped(running)

    def test_a_server_that_dies_mid_run_is_reported_with_its_log_and_the_devices_stop(self):
        process, running, output = self.start_serving()
        (server,) = [pid for pid, command in running.items() if "print_server.py" in command]
        os.kill(server, signal.SIGKILL)
        text = output()
        self.assertEqual(process.returncode, 1, text)
        self.assertIn("the server process stopped with exit code -9", text)
        self.assertIn("server.log", text)
        self.assertNotIn("Traceback", text)
        self.assertStopped(running)

    def test_a_taken_port_fails_before_any_request_and_names_the_flag(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            port = taken.getsockname()[1]
            process = self.start("--once", "--port", str(port))
            stdout, stderr = process.communicate(timeout=RUN_TIMEOUT)
            taken.setblocking(False)
            with self.assertRaises(BlockingIOError, msg="simulate.py connected to the foreign listener"):
                taken.accept()
        self.assertEqual(process.returncode, 1, stdout)
        self.assertIn(f"port {port} on 127.0.0.1 is in use; pass --port", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(list(self.workdir().iterdir()), [], "no config or token is written")
        self.assertNoLeftovers()


class SimulateMainTest(unittest.TestCase):
    def test_a_missing_receipt_app_says_how_to_build_it_before_starting_anything(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as missing, \
                mock.patch.object(simulate, "DIST_DIR", Path(missing) / "dist"), \
                mock.patch.object(simulate.tempfile, "mkdtemp") as mkdtemp, \
                contextlib.redirect_stderr(stderr):
            code = simulate.main(["--once"])
        self.assertEqual(code, 1)
        self.assertIn("make web-build", stderr.getvalue())
        self.assertIn("make setup-web", stderr.getvalue())
        mkdtemp.assert_not_called()

    def serve(self, handler: type) -> str:
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def test_an_api_redirect_fails_and_never_carries_the_token_to_the_other_host(self):
        seen: list[str | None] = []

        class Target(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        target = self.serve(Target)

        class Redirect(Target):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"{target}/stolen")
                self.end_headers()

        origin = self.serve(Redirect)
        with self.assertRaisesRegex(simulate.SimulationError, "failed with 302"):
            simulate._call(f"{origin}/api/printers", "a-secret-admin-token-0000000000")
        self.assertEqual(seen, [])


    def test_a_non_json_answer_is_a_clear_error_not_a_traceback(self):
        class Html(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<html>not the print server</html>")

            def log_message(self, *args):
                pass

        url = f"{self.serve(Html)}/api/printers"
        with self.assertRaisesRegex(simulate.SimulationError, "not JSON"):
            simulate._call(url, "a-secret-admin-token-0000000000")


    def test_stop_signals_every_child_when_one_group_refuses_the_signal(self):
        children = simulate.Children(Path("."))
        processes = [mock.Mock(pid=pid, **{"poll.return_value": None}) for pid in (101, 102, 103)]
        children.processes = dict(zip(("server", "device-home", "device-work"), processes))
        signalled = []

        def killpg(pid, signum):
            signalled.append(pid)
            if pid == 101:
                raise PermissionError(1, "Operation not permitted")

        with mock.patch.object(simulate.os, "killpg", killpg), mock.patch.object(simulate.signal, "signal"):
            children.stop()
        self.assertEqual(signalled, [101, 102, 103])
        for process in processes:
            process.wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()
