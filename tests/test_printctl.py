import asyncio
import base64
import contextlib
import io
import json
import logging
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from aiohttp import web
from PIL import Image

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS.parent / "src" / "scripts"))
sys.path.insert(0, str(_TESTS))

import http_api  # noqa: E402
import printctl  # noqa: E402
from http_api import create_app  # noqa: E402
from job_artifacts import artifacts_root  # noqa: E402
from job_queue import JobQueue, Status  # noqa: E402
from server_config import load_config  # noqa: E402
from test_http_api import (  # noqa: E402
    ADMIN_TOKEN,
    CLIENT_TOKEN,
    HOME_TOKEN,
    OFFICE_TOKEN,
    PHOTO,
    RENDERED,
    SAMPLE_PAYLOAD,
    LogCapture,
    add_frozen_job,
    write_config,
)

SHUTDOWN_SECONDS = 1
ANSI = re.compile(r"\x1b\[")
WRONG_TOKEN = "wrong-token-0123456789abcdef"
SECRETS = [ADMIN_TOKEN, HOME_TOKEN, OFFICE_TOKEN, CLIENT_TOKEN, WRONG_TOKEN]


def http_answer(status: str, content_type: str, body: bytes) -> bytes:
    head = f"HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    return head.encode() + body


class OneShotServer:
    """A raw socket that takes one request and sends ``answer`` (b"" drops it, None never answers)."""

    def __init__(self, answer: bytes | None) -> None:
        self.answer = answer
        self.request: bytes | None = None
        self.done = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(0.2)
        self.url = f"http://127.0.0.1:{self.listener.getsockname()[1]}"
        self.thread = threading.Thread(target=self._serve)

    def _serve(self) -> None:
        while not self.done.is_set():
            try:
                connection, _ = self.listener.accept()
            except TimeoutError:
                continue
            with connection:
                connection.settimeout(5)
                self.request = connection.recv(65536)
                if self.answer is None:
                    self.done.wait(10)
                else:
                    connection.sendall(self.answer)
            return

    def __enter__(self) -> "OneShotServer":
        self.thread.start()
        return self

    def __exit__(self, *_) -> None:
        self.done.set()
        self.thread.join(10)
        self.listener.close()


class ServerThread:
    """The real app on its own loop and thread, because printctl blocks on urllib."""

    def __init__(self, config) -> None:
        self.config = config
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start())
        self.ready.set()
        self.loop.run_forever()

    async def _start(self) -> None:
        # sqlite3 objects belong to the thread that opened them.
        self.queue = JobQueue(self.config.database)
        # After an early 413, aiohttp drains the unread body for up to 10 s, and cleanup waits for it.
        self.runner = web.AppRunner(create_app(self.config, self.queue), access_log=None,
                                    shutdown_timeout=SHUTDOWN_SECONDS)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", 0).start()
        host, port = self.runner.addresses[0][:2]
        self.url = f"http://{host}:{port}"

    def start(self) -> None:
        self.thread.start()
        self.ready.wait(10)

    def call(self, function, *args, **kwargs):
        async def run():
            return function(*args, **kwargs)
        return asyncio.run_coroutine_threadsafe(run(), self.loop).result(10)

    def stop(self) -> None:
        if self.loop.is_closed():
            return

        async def stop():
            await self.runner.cleanup()
            self.queue.close()
            stragglers = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            for task in stragglers:
                task.cancel()
            await asyncio.gather(*stragglers, return_exceptions=True)
        asyncio.run_coroutine_threadsafe(stop(), self.loop).result(SHUTDOWN_SECONDS + 10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)
        self.loop.close()


class Run:
    def __init__(self, status: int, out: str, err: str) -> None:
        self.status, self.out, self.err = status, out, err


class PrintctlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="printctl-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        config = load_config(write_config(self.tmp, access=False))
        config.database.parent.mkdir()
        self.server = ServerThread(config)
        self.server.start()
        self.addCleanup(self.server.stop)
        env = {printctl.TOKEN_ENV: ADMIN_TOKEN, printctl.SERVER_ENV: self.server.url}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NO_COLOR", None)
        self.logs = LogCapture()
        root = logging.getLogger()
        saved = root.handlers[:], root.level
        root.handlers, root.level = [self.logs], logging.DEBUG
        self.addCleanup(lambda: (setattr(root, "handlers", saved[0]), root.setLevel(saved[1])))

    def tearDown(self) -> None:
        for secret in SECRETS:
            self.assertNotIn(secret, self.logs.text())

    def run_cli(self, *argv: str, stdout: io.StringIO | None = None) -> Run:
        out, err = stdout or io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                status = printctl.main(list(argv))
            except SystemExit as exit:
                status = exit.code
        run = Run(status, out.getvalue(), err.getvalue())
        for secret in SECRETS:
            self.assertNotIn(secret, run.out + run.err)
        self.assertNotIn("Traceback", run.err)
        return run

    def ok(self, *argv: str) -> str:
        run = self.run_cli(*argv)
        self.assertEqual(run.status, 0, run.err)
        self.assertEqual(run.err, "")
        return run.out

    def fails(self, *argv: str, status: int = 1) -> str:
        run = self.run_cli(*argv)
        self.assertEqual(run.status, status, run.out)
        self.assertEqual(run.out, "")
        return run.err

    def add_job(self, printer: str = "home", *, title: str = "Holiday photo"):
        return self.server.call(add_frozen_job, self.server.queue, self.server.config.database, printer, title=title)

    def print_png(self, job_id: str) -> bytes:
        return (artifacts_root(self.server.config.database) / job_id / "print.png").read_bytes()

    def print_job(self, job_id: str, printer: str = "home") -> None:
        queue = self.server.queue
        taken = self.server.call(queue.take, printer)
        self.assertEqual(taken.id, job_id)
        self.server.call(queue.mark_sent, job_id)
        self.server.call(queue.confirm, job_id)

    def job(self, job_id: str):
        return self.server.call(self.server.queue.job, job_id)


class SendTest(PrintctlTestCase):
    def test_send_image_queues_the_file_with_title_and_expiry(self):
        photo = self.tmp / "photo.png"
        photo.write_bytes(PHOTO)
        out = self.ok("send", "image", str(photo), "--printer", "office", "--title", "Beach", "--expires", "2h")
        job_id = re.search(r"Queued (\w+) for office", out)[1]
        job = self.job(job_id)
        self.assertEqual((job.printer, job.kind, job.title, job.source, job.ingress),
                         ("office", "image", "Beach", "admin", "cli"))
        self.assertEqual(round(job.expires_at - job.created_at), 7200)
        self.assertEqual(self.print_png(job_id), RENDERED.png)
        self.assertIn(f"{job.paper_mm / 10:.1f} cm", out)

    def test_send_receipt_posts_the_payload_unchanged(self):
        received = []

        def fake_render(kind, *, payload=None, image=None):
            received.append((kind, payload))
            return RENDERED

        sample = self.tmp / "receipt.json"
        sample.write_text(json.dumps(SAMPLE_PAYLOAD), encoding="utf-8")
        with mock.patch.object(http_api, "render", side_effect=fake_render):
            out = self.ok("send", "receipt", str(sample), "--printer", "home")
        self.assertEqual(received, [("receipt", SAMPLE_PAYLOAD)])
        job = self.job(re.search(r"Queued (\w+) for home", out)[1])
        self.assertEqual(round(job.expires_at - job.created_at), 3600)

    def test_send_template_queues_a_template_job_and_reports_a_bad_template_with_the_server_message(self):
        sample = _TESTS.parent / "samples" / "templates" / "ticket.json"
        out = self.ok("send", "template", str(sample), "--printer", "home", "--title", "OPS-2481")
        job = self.job(re.search(r"Queued (\w+) for home", out)[1])
        self.assertEqual((job.kind, job.title, job.width), ("template", "OPS-2481", 384))

        unknown = self.tmp / "unknown.json"
        unknown.write_text(json.dumps({**json.loads(sample.read_text(encoding="utf-8")), "template": "nope"}),
                           encoding="utf-8")
        err = self.fails("send", "template", str(unknown), "--printer", "home")
        self.assertIn('unknown template "nope"', err)
        self.assertIn("(HTTP 422)", err)
        self.assertEqual([queued.id for queued in self.server.call(self.server.queue.jobs)], [job.id])

    def test_send_text_queues_native_text_and_refuses_a_template_without_a_text_mode(self):
        templates = _TESTS.parent / "samples" / "templates"
        out = self.ok("send", "text", str(templates / "build.json"), "--printer", "home", "--title", "NIGHTLY")
        job = self.job(re.search(r"Queued (\w+) for home", out)[1])
        self.assertEqual((job.kind, job.title, job.width), ("text", "NIGHTLY", 384))
        data = self.server.call(self.server.queue.take, "home").data
        self.assertTrue(data.startswith(b"\x1b@"))
        self.assertNotIn(b"\x1dv0", data)

        err = self.fails("send", "text", str(templates / "ticket.json"), "--printer", "home")
        self.assertIn('template "ticket" has no text mode', err)
        self.assertIn("(HTTP 422)", err)
        self.assertEqual([queued.id for queued in self.server.call(self.server.queue.jobs)], [job.id])

    def test_expires_accepts_minutes_hours_and_days_only(self):
        for text, seconds in {"30m": 1800, "2h": 7200, "1d": 86400, "45M": 2700}.items():
            self.assertEqual(printctl.expiry_seconds(text), seconds)
        photo = self.tmp / "photo.png"
        photo.write_bytes(PHOTO)
        for bad in ["90", "0m", "2w", "-1h", "1.5h"]:
            with self.subTest(bad=bad):
                err = self.fails("send", "image", str(photo), "--printer", "home", f"--expires={bad}", status=2)
                self.assertIn("30m, 2h, 1d", err)

    def test_send_refuses_a_receipt_file_that_is_not_a_json_object(self):
        for name, content in {"broken.json": "{\"blocks\": [", "list.json": "[1, 2]"}.items():
            path = self.tmp / name
            path.write_text(content, encoding="utf-8")
            self.assertIn(name, self.fails("send", "receipt", str(path), "--printer", "home"))
        self.assertIn("missing.png", self.fails("send", "image", str(self.tmp / "missing.png"), "--printer", "home"))
        self.assertEqual(self.server.call(self.server.queue.jobs), [])

    def test_send_reports_the_server_error_for_an_unknown_printer(self):
        photo = self.tmp / "photo.png"
        photo.write_bytes(PHOTO)
        self.assertIn("unknown printer (HTTP 404)", self.fails("send", "image", str(photo), "--printer", "garage"))

    def test_send_reports_a_file_that_is_not_an_image(self):
        text = self.tmp / "notes.txt"
        text.write_text("not a picture", encoding="utf-8")
        self.assertIn("(HTTP 422)", self.fails("send", "image", str(text), "--printer", "home"))


class JobsTest(PrintctlTestCase):
    def test_jobs_lists_newest_first_with_filters(self):
        first = self.add_job("home", title="First")
        second = self.add_job("office", title="Second")
        third = self.add_job("home", title="Third")
        self.print_job(first.id)

        lines = self.ok("jobs").splitlines()
        self.assertEqual(lines[0].split()[:3], ["ID", "PRINTER", "STATUS"])
        self.assertEqual([line.split()[0] for line in lines[1:]], [third.id, second.id, first.id])

        home = self.ok("jobs", "--printer", "home")
        self.assertNotIn(second.id, home)
        self.assertIn(first.id, home)
        queued = self.ok("jobs", "--status", "queued")
        self.assertNotIn(first.id, queued)
        self.assertIn(third.id, queued)
        self.assertEqual(len(self.ok("jobs", "--limit", "1").splitlines()), 2)

    def test_jobs_rows_carry_sizes_and_ages(self):
        job = self.add_job()
        row = self.ok("jobs").splitlines()[1]
        self.assertIn(f"{job.paper_mm / 10:.1f} cm", row)
        self.assertIn(printctl.human_size(job.size_bytes), row)
        self.assertIn("just now", row)

    def test_jobs_says_so_when_nothing_matches(self):
        self.assertEqual(self.ok("jobs"), "No jobs match.\n")

    def test_jobs_reports_a_bad_status_filter(self):
        self.assertIn("status must be one of", self.fails("jobs", "--status", "lost"))


class JobCommandsTest(PrintctlTestCase):
    def test_show_prints_the_job_and_its_timeline_in_local_time(self):
        job = self.add_job()
        self.print_job(job.id)
        out = self.ok("show", job.id)
        self.assertIn("Holiday photo", out)
        self.assertIn(f"{job.width} x {job.height} dots", out)
        timeline = [line.split()[2] for line in out.split("TIME", 1)[1].splitlines()[1:]]
        stored = [event.event.value for event in self.job(job.id).events]
        self.assertEqual(timeline, stored)
        self.assertEqual(timeline[-1], "printed")
        self.assertIn(printctl.local_time(self.job(job.id).printed_at), out)

    def test_show_prints_the_artifact_folder_or_says_it_is_missing(self):
        job = self.add_job()
        folder = artifacts_root(self.server.config.database) / job.id
        self.assertRegex(self.ok("show", job.id), rf"\nartifacts +{re.escape(str(folder))}\n")
        shutil.rmtree(folder)
        self.assertRegex(self.ok("show", job.id), r"\nartifacts +missing on the server\n")

    def test_show_reports_an_unknown_job(self):
        self.assertIn("unknown job (HTTP 404)", self.fails("show", "nosuchjob"))

    def test_image_saves_the_stored_png(self):
        job = self.add_job()
        target = self.tmp / "out.png"
        out = self.ok("image", job.id, "-o", str(target))
        self.assertEqual(target.read_bytes(), RENDERED.png)
        with Image.open(target) as image:
            self.assertEqual(image.size, (RENDERED.width, RENDERED.height))
        self.assertIn(str(target), out)

    def test_cancel_cancels_once_and_then_reports_the_state(self):
        job = self.add_job()
        self.assertIn(f"Cancelled {job.id}", self.ok("cancel", job.id))
        self.assertEqual(self.job(job.id).status, Status.CANCELLED)
        self.assertIn("already cancelled (HTTP 409)", self.fails("cancel", job.id))

    def test_reprint_queues_a_finished_job_again_on_another_printer(self):
        job = self.add_job("home")
        self.assertIn("still queued (HTTP 409)", self.fails("reprint", job.id))
        self.print_job(job.id)
        out = self.ok("reprint", job.id, "--printer", "office")
        copy = self.job(re.search(r"Queued (\w+) for office", out)[1])
        self.assertEqual((copy.printer, copy.status, copy.source), ("office", Status.QUEUED, "admin"))
        self.assertEqual(self.print_png(copy.id), RENDERED.png)
        same = self.job(re.search(r"Queued (\w+) for home", self.ok("reprint", job.id))[1])
        self.assertEqual(same.printer, "home")


class PrinterCommandsTest(PrintctlTestCase):
    def test_clear_cancels_only_that_printers_queue(self):
        home = [self.add_job("home") for _ in range(2)]
        office = self.add_job("office")
        self.assertIn("Cancelled 2 queued jobs on home", self.ok("clear", "home"))
        self.assertEqual({self.job(job.id).status for job in home}, {Status.CANCELLED})
        self.assertEqual(self.job(office.id).status, Status.QUEUED)
        self.assertIn("Cancelled 0 queued jobs", self.ok("clear", "home"))

    def test_move_moves_queued_jobs(self):
        jobs = [self.add_job("home") for _ in range(3)]
        self.assertIn("Moved 3 queued jobs from home to office", self.ok("move", "home", "office"))
        self.assertEqual({self.job(job.id).printer for job in jobs}, {"office"})
        self.assertIn("to must be another printer", self.fails("move", "office", "office"))
        self.assertIn("unknown printer", self.fails("move", "office", "garage"))

    def test_printers_shows_state_queue_and_last_seen(self):
        self.add_job("office")
        self.print_job(self.add_job("home").id)
        seen = time.time() - 300
        self.server.call(self.server.queue.update_printer_state, "home", last_seen=seen, latency_ms=42.4,
                         route="tunnel", client_version="1.2.0")
        lines = self.ok("printers").splitlines()
        self.assertEqual(lines[0].split()[:4], ["ID", "NAME", "PLACE", "STATE"])
        home = next(line for line in lines if line.startswith("home"))
        office = next(line for line in lines if line.startswith("office"))
        for expected in ["offline", "5 min ago", "42 ms", "tunnel", "1.2.0"]:
            self.assertIn(expected, home)
        self.assertEqual(re.split(r"\s{2,}", office)[4:6], ["1", "0"])
        self.assertEqual(re.split(r"\s{2,}", home)[4:6], ["0", "1"])

    def test_stats_shows_totals_and_an_hourly_line_per_printer(self):
        printed = self.add_job("home")
        self.print_job(printed.id)
        self.add_job("office")
        out = self.ok("stats")
        self.assertRegex(out, r"printed today\s+1\n")
        self.assertRegex(out, r"queued\s+1\n")
        self.assertIn(printctl.paper(printed.paper_mm), out)
        home = next(line for line in out.splitlines() if line.startswith("home"))
        spark = home.split()[1]
        self.assertEqual(len(spark), 24)
        self.assertEqual(spark[-1], printctl.SPARK[-1])
        self.assertEqual(home.split()[2], "1")


class FailureTest(PrintctlTestCase):
    def test_wrong_token_prints_the_server_error_and_a_hint(self):
        os.environ[printctl.TOKEN_ENV] = WRONG_TOKEN
        err = self.fails("jobs")
        self.assertIn("no valid credential (HTTP 401)", err)
        self.assertIn(printctl.TOKEN_ENV, err)
        self.assertNotIn(WRONG_TOKEN, err)

    def test_a_client_token_is_refused_for_admin_commands(self):
        os.environ[printctl.TOKEN_ENV] = CLIENT_TOKEN
        self.assertIn("admin only (HTTP 403)", self.fails("printers"))

    def test_token_file_takes_precedence_over_the_environment(self):
        os.environ[printctl.TOKEN_ENV] = WRONG_TOKEN
        token_file = self.tmp / "admin-token"
        token_file.write_text(ADMIN_TOKEN + "\n", encoding="utf-8")
        self.assertIn("ID", self.ok("--token-file", str(token_file), "printers"))
        self.assertIn("Cannot read the token file", self.fails("--token-file", str(self.tmp / "nope"), "stats",
                                                               status=2))
        empty = self.tmp / "empty"
        empty.write_text("\n", encoding="utf-8")
        self.assertIn("is empty", self.fails("--token-file", str(empty), "stats", status=2))

    def test_a_missing_token_is_refused_before_any_request(self):
        del os.environ[printctl.TOKEN_ENV]
        err = self.fails("stats", status=2)
        self.assertIn(printctl.TOKEN_ENV, err)
        self.assertIn("--token-file", err)

    def test_server_url_comes_from_flag_then_env_then_default(self):
        self.assertEqual(printctl.server_url("http://flag:1"), "http://flag:1")
        self.assertEqual(printctl.server_url(None), self.server.url)
        del os.environ[printctl.SERVER_ENV]
        self.assertEqual(printctl.server_url(None), printctl.DEFAULT_SERVER)
        os.environ[printctl.SERVER_ENV] = "http://127.0.0.1:1"
        self.assertIn("ID", self.ok("--server", self.server.url + "/", "printers"))

    def test_unreachable_server_names_the_url_and_how_to_start_it(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            url = f"http://127.0.0.1:{probe.getsockname()[1]}"
        err = self.fails("--server", url, "jobs")
        self.assertIn(f"not reachable at {url}", err)
        self.assertIn("print_server.py --config", err)

    def test_invalid_server_url_is_reported(self):
        self.assertIn("not a valid server URL", self.fails("--server", "print.example.com", "jobs"))

    def test_a_proxy_error_page_or_a_dropped_connection_is_reported(self):
        answers = {
            "502 page": http_answer("502 Bad Gateway", "text/html", b"<h1>502</h1>\n"),
            "dropped": b"",
        }
        for name, answer in answers.items():
            with self.subTest(name), OneShotServer(answer) as server:
                err = self.fails("--server", server.url, "stats")
                self.assertIn(server.url, err)
                self.assertIn("print_server.py --config", err)
                if name == "502 page":
                    self.assertIn("HTTP 502", err)

    def test_a_redirect_is_refused_and_never_carries_the_token(self):
        photo = self.tmp / "photo.png"
        photo.write_bytes(PHOTO)
        commands = {"GET": (["jobs"], "/api/jobs?limit=20"),
                    "POST": (["send", "image", str(photo), "--printer", "home"], "/api/jobs")}
        for code in [301, 302, 303, 307, 308]:
            for method, (argv, path) in commands.items():
                for same_path in [True, False]:
                    with self.subTest(code=code, method=method, same_path=same_path), \
                            OneShotServer(b"") as elsewhere:
                        location = f"{elsewhere.url}{path}" if same_path else f"{elsewhere.url}/login"
                        moved = f"HTTP/1.1 {code} Moved\r\nLocation: {location}\r\nContent-Length: 0\r\n" \
                                f"Connection: close\r\n\r\n".encode()
                        with OneShotServer(moved) as first:
                            err = self.fails("--server", first.url, *argv)
                        if same_path:
                            self.assertIn(f"HTTP {code} and redirected to {elsewhere.url}; pass that URL with "
                                          f"--server", err)
                        else:
                            self.assertIn(f"HTTP {code} and redirected to {location}; check --server", err)
                        self.assertNotIn("print_server.py", err)
                        self.assertIn(ADMIN_TOKEN.encode(), first.request)
                        self.assertIsNone(elsewhere.request)

    def test_a_redirect_urllib_does_not_handle_is_reported_as_a_redirect(self):
        answer = b"HTTP/1.1 300 Multiple Choices\r\nLocation: http://127.0.0.1:1/x\r\nContent-Length: 0\r\n" \
                 b"Connection: close\r\n\r\n"
        with OneShotServer(answer) as first:
            err = self.fails("--server", first.url, "stats")
        self.assertIn("HTTP 300 and redirected to http://127.0.0.1:1/x; check --server", err)
        self.assertNotIn("print_server.py", err)

    def test_no_answer_in_time_is_reported_with_a_retry_warning_for_writes(self):
        with mock.patch.object(printctl, "TIMEOUT_SECONDS", 0.3):
            for argv, warns in [(["stats"], False), (["cancel", "abcd1234"], True)]:
                with self.subTest(argv[0]), OneShotServer(None) as silent:
                    err = self.fails("--server", silent.url, *argv)
                    self.assertIn(f"{silent.url} sent no answer within 0.3 s", err)
                    self.assertEqual("check `printctl jobs` before you retry" in err, warns)

    def test_a_client_timeout_overrides_the_default(self):
        with OneShotServer(None) as silent:
            client = printctl.Client(silent.url, ADMIN_TOKEN, timeout=0.3)
            with self.assertRaisesRegex(printctl.Failure, r"no answer within 0\.3 s"):
                client.request("GET", "/api/stats")

    def test_a_token_that_cannot_be_a_header_is_refused_without_printing_it(self):
        token_file = self.tmp / "admin-token"
        for name, token in {"line break": ADMIN_TOKEN[:10] + "\n" + ADMIN_TOKEN[10:],
                            "space": ADMIN_TOKEN[:10] + " " + ADMIN_TOKEN[10:],
                            "non-ASCII": ADMIN_TOKEN + "\u00e9"}.items():
            with self.subTest(name):
                os.environ[printctl.TOKEN_ENV] = token
                err = self.fails("jobs", status=2)
                self.assertIn(f"admin token in {printctl.TOKEN_ENV} has a space, a line break", err)
                self.assertNotIn(token, err)
                token_file.write_text(token, encoding="utf-8")
                self.assertIn(f"admin token in the token file {token_file}", self.fails(
                    "--token-file", str(token_file), "jobs", status=2))

    def test_an_image_over_the_body_limit_is_refused_before_upload(self):
        big = self.tmp / "huge.png"
        big.write_bytes(b"\x89PNG" + b"\0" * printctl.MAX_IMAGE_BYTES)
        err = self.fails("send", "image", str(big), "--printer", "home")
        self.assertIn("up to 7.5 MB", err)
        self.assertEqual(self.server.call(self.server.queue.jobs), [])
        encoded = len(base64.b64encode(b"\0" * printctl.MAX_IMAGE_BYTES))
        self.assertLess(encoded + 1024, http_api.MAX_BODY_BYTES)

    def test_a_body_over_10_mb_gets_the_server_error_and_the_server_still_stops_promptly(self):
        huge = self.tmp / "huge.json"
        huge.write_text(json.dumps({**SAMPLE_PAYLOAD, "padding": "x" * (11 * 1024 * 1024)}), encoding="utf-8")
        self.assertIn("HTTP 413", self.fails("send", "receipt", str(huge), "--printer", "home"))
        started = time.monotonic()
        self.server.stop()
        self.assertLess(time.monotonic() - started, SHUTDOWN_SECONDS + 2)

    def test_image_refuses_an_answer_that_is_not_a_png(self):
        page = http_answer("200 OK", "text/html", b"<html>login</html>")
        target = self.tmp / "out.png"
        with OneShotServer(page) as portal:
            err = self.fails("--server", portal.url, "image", "abcd1234", "-o", str(target))
        self.assertIn("sent text/html, not image/png", err)
        self.assertFalse(target.exists())


class OutputTest(PrintctlTestCase):
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    def test_colour_only_on_a_terminal_without_no_color(self):
        self.add_job()
        self.assertIsNone(ANSI.search(self.ok("jobs")))
        terminal = self.run_cli("jobs", stdout=self.Terminal())
        self.assertRegex(terminal.out, ANSI)
        os.environ["NO_COLOR"] = "1"
        self.assertIsNone(ANSI.search(self.run_cli("jobs", stdout=self.Terminal()).out))

    def test_coloured_columns_stay_aligned(self):
        self.print_job(self.add_job("home").id)
        self.add_job("home")
        plain = self.ok("jobs")
        coloured = self.run_cli("jobs", stdout=self.Terminal()).out
        self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", coloured), plain)

    def test_human_formats(self):
        self.assertEqual(printctl.human_size(812), "812 B")
        self.assertEqual(printctl.human_size(59_400), "58 KB")
        self.assertEqual(printctl.human_size(3_250_000), "3.1 MB")
        self.assertEqual(printctl.human_size(1_048_575), "1.0 MB")
        self.assertEqual(printctl.human_size(1_048_000), "1023 KB")
        self.assertEqual(printctl.paper(154.0), "15.4 cm")
        now = 1_800_000_000
        self.assertEqual(printctl.age(now - 3, now), "just now")
        self.assertEqual(printctl.age(now - 200, now), "3 min ago")
        self.assertEqual(printctl.age(now - 7300, now), "2 h ago")
        self.assertEqual(printctl.age(now + 3600, now), "in 1 h")
        self.assertEqual(printctl.age(now + 7199, now), "in 2 h")
        self.assertEqual(printctl.age(now + 86399, now), "in 1 d")
        self.assertEqual(printctl.age(now - 3599, now), "1 h ago")
        self.assertEqual(printctl.age(now - 59.6, now), "1 min ago")
        self.assertEqual(printctl.age(None, now), "-")

    def test_client_repr_hides_the_token(self):
        self.assertNotIn(ADMIN_TOKEN, repr(printctl.Client(self.server.url, ADMIN_TOKEN)))


if __name__ == "__main__":
    unittest.main()
