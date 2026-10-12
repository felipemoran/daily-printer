import asyncio
import base64
import io
import json
import logging
import shutil
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, ImageDraw

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

import http_api  # noqa: E402
from access_auth import HEADER, AccessVerifier  # noqa: E402
from http_api import HUB, create_app  # noqa: E402
from job_queue import JobQueue, Status  # noqa: E402
from render_job import escpos_from_png, render  # noqa: E402
from server_config import load_config  # noqa: E402
from test_access_auth import AUDIENCE, KEY_A, STRANGER, TEAM, FakeCerts, claims, sign  # noqa: E402

ADMIN_TOKEN = "admin-token-7f3c9a1e5b2d4f6a8c0e"
HOME_TOKEN = "home-printer-token-2b4d6f8a0c1e3a5c"
OFFICE_TOKEN = "office-printer-token-9e7c5a3b1d0f2e4a"
CLIENT_TOKEN = "morning-brief-token-4a6c8e0b2d4f6a8c"
ADMIN_EMAIL = "boss@example.com"
SENDER_EMAIL = "friend@example.com"
SAMPLE_PAYLOAD = json.loads((_TESTS.parent / "samples" / "receipt-sample.json").read_text(encoding="utf-8"))


def write_config(directory: Path, *, access: bool = True, web_rate_limit: int = 10) -> Path:
    access_table = f"""
[access]
team_domain = "{TEAM}"
audience = "{AUDIENCE}"
web_rate_limit = {web_rate_limit}
admin_emails = ["{ADMIN_EMAIL}"]
""" if access else ""
    path = directory / "server.toml"
    path.write_text(f"""
[server]
host = "127.0.0.1"
port = 8787
database = "data/queue.db"
admin_token = "{ADMIN_TOKEN}"
{access_table}
[printers.home]
name = "Home"
place = "Home office"
token = "{HOME_TOKEN}"
public = true

[printers.office]
name = "Office"
place = "Desk at work"
token = "{OFFICE_TOKEN}"

[clients.morning-brief]
token = "{CLIENT_TOKEN}"
""")
    path.chmod(0o600)
    return path


def photo_png(size: tuple[int, int] = (640, 480)) -> bytes:
    """A gradient with shapes and mid-tones, as a phone upload would carry."""
    width, height = size
    picture = Image.merge("RGB", (
        Image.linear_gradient("L").resize(size),
        Image.linear_gradient("L").rotate(90).resize(size),
        Image.radial_gradient("L").resize(size),
    ))
    draw = ImageDraw.Draw(picture)
    draw.ellipse((width // 5, height // 5, width // 2, height // 2), fill="black")
    draw.rectangle((width // 2, height // 2, width - 10, height - 10), fill="white")
    out = io.BytesIO()
    picture.save(out, format="PNG")
    return out.getvalue()


PHOTO = photo_png()
RENDERED = render("image", image=PHOTO)


class LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))

    def text(self) -> str:
        return "\n".join(self.lines)


class ServerTestCase(unittest.IsolatedAsyncioTestCase):
    """The real app on a temp SQLite file, fake Access keys, and a check that no secret leaks."""

    access = True
    web_rate_limit = 10

    async def asyncSetUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="print-server-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.logs = LogCapture()
        root = logging.getLogger()
        saved = root.handlers[:], root.level
        root.handlers, root.level = [self.logs], logging.DEBUG
        self.addCleanup(lambda: (setattr(root, "handlers", saved[0]), root.setLevel(saved[1])))
        self.secrets = [ADMIN_TOKEN, HOME_TOKEN, OFFICE_TOKEN, CLIENT_TOKEN]

        self.config = load_config(write_config(self.tmp, access=self.access, web_rate_limit=self.web_rate_limit))
        self.config.database.parent.mkdir()
        self.queue = JobQueue(self.config.database)
        self.addCleanup(self.queue.close)
        self.certs = FakeCerts({"a": KEY_A})
        self.app = create_app(self.config, self.queue, verifier=AccessVerifier(TEAM, AUDIENCE, keys=self.certs))
        self.hub = self.app[HUB]
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def asyncTearDown(self) -> None:
        logs = self.logs.text()
        for secret in self.secrets:
            self.assertNotIn(secret, logs)

    def bearer(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def web(self, email: str = SENDER_EMAIL, **overrides) -> dict:
        token = sign(claims(email=email, **overrides))
        self.secrets.append(token)
        return {HEADER: token}

    async def call(self, method: str, path: str, headers: dict | None = None, *, body=None,
                   data=None) -> tuple[int, object]:
        response = await self.client.request(method, path, headers=headers or {}, json=body, data=data)
        raw = await response.read()
        for secret in self.secrets:
            self.assertNotIn(secret.encode(), raw)
        if response.content_type == "application/json":
            parsed = json.loads(raw)
            if response.status >= 400:
                self.assertEqual(list(parsed), ["error"])
                self.assertNotIn("Traceback", parsed["error"])
            return response.status, parsed
        return response.status, raw

    def add_job(self, printer: str = "home", *, expires_in: float = 3600, rendered=RENDERED):
        return self.queue.add(
            printer, rendered.escpos, kind="image", title="Holiday photo", source="morning-brief", ingress="api",
            png=rendered.png, width=rendered.width, height=rendered.height, render_ms=rendered.render_ms,
            expires_in=expires_in,
        )

    def image_job(self, printer: str = "home", **extra) -> dict:
        return {"printer": printer, "kind": "image", "title": "Holiday photo",
                "image": base64.b64encode(PHOTO).decode(), **extra}

    def assertEventsMatchStatus(self, job_id: str) -> None:
        job = self.queue.job(job_id)
        events = [event.event for event in job.events]
        self.assertEqual(events.count("sending"), job.attempts)
        final = {Status.PRINTED, Status.FAILED, Status.EXPIRED, Status.CANCELLED}
        if job.status in final:
            self.assertEqual(events[-1], job.status.value)
        else:
            self.assertNotIn(events[-1], [status.value for status in final])


ADMIN_ROUTES = [
    ("GET", "/api/jobs"),
    ("GET", "/api/jobs/abcd1234"),
    ("GET", "/api/jobs/abcd1234/image"),
    ("POST", "/api/jobs/abcd1234/cancel"),
    ("POST", "/api/jobs/abcd1234/reprint"),
    ("POST", "/api/printers/home/clear"),
    ("POST", "/api/printers/home/move"),
    ("GET", "/api/printers"),
    ("GET", "/api/stats"),
    ("GET", "/api/clients"),
    ("GET", "/api/server"),
]
WEB_ROUTES = [("GET", "/api/me"), ("GET", "/")]
ALL_ROUTES = [("POST", "/api/jobs")] + ADMIN_ROUTES + WEB_ROUTES


class IdentityTest(ServerTestCase):
    async def assertEveryRoute(self, headers: dict, status: int, routes=ALL_ROUTES) -> None:
        for method, path in routes:
            with self.subTest(method=method, path=path):
                got, body = await self.call(method, path, headers, body=self.image_job("office"))
                self.assertEqual(got, status, body)
        self.assertEqual(self.queue.jobs(), [])

    async def test_every_route_refuses_a_request_without_credentials(self):
        await self.assertEveryRoute({}, 401)

    async def test_every_route_refuses_a_wrong_bearer_token(self):
        await self.assertEveryRoute(self.bearer("not-a-token-of-this-server-000000"), 401)

    async def test_a_printer_token_is_not_an_http_credential(self):
        await self.assertEveryRoute(self.bearer(HOME_TOKEN), 401)

    async def test_cf_connecting_ip_grants_nothing(self):
        await self.assertEveryRoute({"Cf-Connecting-IP": "127.0.0.1", "X-Forwarded-For": "127.0.0.1"}, 401)

    async def test_forged_access_assertions_are_refused(self):
        forged = {
            "unknown key": sign(claims(), key=STRANGER, kid="a"),
            "wrong audience": sign(claims(aud=["another-app"])),
            "wrong issuer": sign(claims(iss="https://evil.cloudflareaccess.com")),
            "expired": sign(claims(exp=int(time.time()) - 600)),
            "unsigned": sign(claims()).rsplit(".", 1)[0] + ".",
            "admin email, wrong key": sign(claims(email=ADMIN_EMAIL), key=STRANGER, kid="a"),
        }
        self.secrets.extend(forged.values())
        for name, token in forged.items():
            with self.subTest(name):
                await self.assertEveryRoute({HEADER: token}, 401)

    async def test_admin_routes_refuse_a_client_token(self):
        await self.assertEveryRoute(self.bearer(CLIENT_TOKEN), 403, ADMIN_ROUTES + WEB_ROUTES)

    async def test_admin_routes_refuse_a_web_sender(self):
        await self.assertEveryRoute(self.web(), 403, ADMIN_ROUTES)

    async def test_web_routes_refuse_the_admin_token(self):
        await self.assertEveryRoute(self.bearer(ADMIN_TOKEN), 403, WEB_ROUTES)

    async def test_admin_email_has_admin_rights(self):
        for path in ("/api/printers", "/api/stats", "/api/jobs"):
            with self.subTest(path=path):
                status, _ = await self.call("GET", path, self.web(ADMIN_EMAIL.upper()))
                self.assertEqual(status, 200)

    async def test_web_sender_cannot_print_on_a_non_public_printer(self):
        status, _ = await self.call("POST", "/api/jobs", self.web(), body=self.image_job("office"))
        self.assertEqual(status, 403)
        self.assertEqual(self.queue.jobs(), [])

    async def test_me_lists_the_email_and_only_public_printers(self):
        status, body = await self.call("GET", "/api/me", self.web())
        self.assertEqual(status, 200)
        home = {"id": "home", "name": "Home", "place": "Home office"}
        self.assertEqual(body, {"email": SENDER_EMAIL, "printers": [home]})

    async def test_index_serves_html_to_a_web_sender(self):
        status, body = await self.call("GET", "/", self.web())
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body)

    async def test_unknown_route_is_a_json_404(self):
        status, body = await self.call("GET", "/api/nothing-here", self.bearer(ADMIN_TOKEN))
        self.assertEqual((status, body), (404, {"error": "Not Found"}))


class NoAccessConfigTest(ServerTestCase):
    access = False

    async def test_web_senders_are_refused_without_an_access_table(self):
        for method, path in [("POST", "/api/jobs")] + WEB_ROUTES:
            with self.subTest(path=path):
                status, _ = await self.call(method, path, self.web(), body=self.image_job())
                self.assertEqual(status, 401)
        self.assertEqual(self.queue.jobs(), [])


class IntakeTest(ServerTestCase):
    web_rate_limit = 2

    async def test_image_job_is_rendered_queued_and_attributed_to_its_sender(self):
        senders = [
            (self.bearer(CLIENT_TOKEN), "office", "morning-brief", "api"),
            (self.bearer(ADMIN_TOKEN), "office", "admin", "cli"),
            (self.web(ADMIN_EMAIL), "office", ADMIN_EMAIL, "admin-web"),
            (self.web(), "home", SENDER_EMAIL, "web"),
        ]
        for headers, printer, source, ingress in senders:
            with self.subTest(ingress=ingress):
                status, body = await self.call("POST", "/api/jobs", headers, body=self.image_job(printer))
                self.assertEqual(status, 201, body)
                self.assertEqual((body["printer"], body["source"], body["ingress"]), (printer, source, ingress))
                self.assertEqual((body["status"], body["kind"], body["width"]), ("queued", "image", 384))
                self.assertEqual(body["paper_mm"], body["height"] / 8)
                png = self.queue.png(body["id"])
                self.assertEqual(png, RENDERED.png)
                self.assertEqual(body["size_bytes"], len(escpos_from_png(png)))
                self.assertAlmostEqual(body["expires_at"] - body["created_at"], 3600)
                self.assertEventsMatchStatus(body["id"])
        taken = self.queue.take("home")
        self.assertEqual(taken.data, escpos_from_png(self.queue.png(taken.id)))

    async def test_receipt_job_renders_the_sample_payload(self):
        body = {"printer": "office", "kind": "receipt", "title": "Today", "payload": SAMPLE_PAYLOAD, "expires_in": 600}
        status, job = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=body)
        self.assertEqual(status, 201, job)
        self.assertEqual((job["kind"], job["width"]), ("receipt", 384))
        self.assertGreater(job["height"], 400)
        self.assertAlmostEqual(job["expires_at"] - job["created_at"], 600)

    async def test_invalid_envelopes_are_400_and_queue_nothing(self):
        image = self.image_job()
        cases = {
            "not JSON": b"{printer: home",
            "not an object": b'["home"]',
            "invalid UTF-8": b'{"printer": "\xff"}',
            "deep nesting": b"[" * 100_000 + b"]" * 100_000,
            "no printer": {**image, "printer": None},
            "printer not text": {**image, "printer": ["home"]},
            "unknown kind": {**image, "kind": "pdf"},
            "kind not text": {**image, "kind": {"a": 1}},
            "title not text": {**image, "title": 12},
            "title too long": {**image, "title": "x" * 201},
            "expires_in zero": {**image, "expires_in": 0},
            "expires_in negative": {**image, "expires_in": -60},
            "expires_in under 1": {**image, "expires_in": 0.5},
            "expires_in true": {**image, "expires_in": True},
            "expires_in text": {**image, "expires_in": "3600"},
            "expires_in over 7 days": {**image, "expires_in": 7 * 86400 + 1},
            "expires_in NaN": json.dumps({**image, "expires_in": float("nan")}).encode(),
            "image missing": {**image, "image": None},
            "image empty": {**image, "image": ""},
            "image not base64": {**image, "image": "not base64!"},
            "image non-ASCII": {**image, "image": "aGVsbG8é"},
            "receipt without payload": {"printer": "home", "kind": "receipt"},
            "receipt payload a list": {"printer": "home", "kind": "receipt", "payload": [1]},
        }
        for name, case in cases.items():
            with self.subTest(name):
                options = {"data": case} if isinstance(case, bytes) else {"body": case}
                status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), **options)
                self.assertEqual(status, 400, body)
        self.assertEqual(self.queue.jobs(), [])

    async def test_unknown_printer_is_404(self):
        status, _ = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job("garage"))
        self.assertEqual(status, 404)

    async def test_unreadable_image_is_422_with_the_render_message(self):
        job = self.image_job(image=base64.b64encode(b"GIF89a but not really").decode())
        status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=job)
        self.assertEqual(status, 422)
        self.assertIn("not an image this server can read", body["error"])
        self.assertEqual(self.queue.jobs(), [])

    async def test_image_too_tall_is_422(self):
        job = self.image_job(image=base64.b64encode(photo_png((200, 2400))).decode())
        status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=job)
        self.assertEqual(status, 422)
        self.assertIn("cm long", body["error"])

    async def test_unexpected_render_failure_is_a_generic_500_with_a_logged_traceback(self):
        failure = RuntimeError("/Users/secret/path exploded")
        with mock.patch.object(http_api, "render", side_effect=failure):
            status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job())
        self.assertEqual(status, 500)
        self.assertNotIn("secret", body["error"])
        self.assertIn("Traceback", self.logs.text())
        self.assertEqual(self.queue.jobs(), [])

    async def test_template_envelope_fault_is_422_and_server_fault_is_generic_500(self):
        ticket = json.loads((_TESTS.parent / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))
        job = {"printer": "home", "kind": "template", "payload": {**ticket, "template": "nope"}}
        status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=job)
        self.assertEqual(status, 422, body)
        self.assertIn('unknown template "nope"', body["error"])
        fault = RuntimeError("server fault: render.html has no renderTemplate; rebuild web/dist")
        with mock.patch("render_job.capture_template", side_effect=fault):
            job = {**job, "payload": ticket}
            status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=job)
        self.assertEqual(status, 500, body)
        self.assertEqual(body["error"], "rendering failed on the server")
        self.assertEqual(self.queue.jobs(), [])

    async def test_payload_nested_150_deep_is_422_before_chromium_launches(self):
        ticket = json.loads((_TESTS.parent / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))
        deep: dict = {}
        for _ in range(150):
            deep = {"x": deep}
        payload = {**ticket, "data": {**ticket["data"], "deep": deep}}
        for kind in ("template", "text"):
            with self.subTest(kind), mock.patch("render_job.sync_playwright") as playwright:
                job = {"printer": "home", "kind": kind, "payload": payload}
                status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=job)
                self.assertEqual(status, 422, body)
                self.assertEqual(body["error"], "payload: nested more than 32 levels deep")
                playwright.assert_not_called()
        self.assertEqual(self.queue.jobs(), [])

    async def test_body_over_10_mb_is_413(self):
        oversized = json.dumps(self.image_job(image="A" * (10 * 1024 * 1024))).encode()
        status, body = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), data=io.BytesIO(oversized))
        self.assertEqual(status, 413, body)
        self.assertEqual(self.queue.jobs(), [])

    async def test_web_rate_limit_is_per_email(self):
        statuses = []
        for _ in range(3):
            status, _ = await self.call("POST", "/api/jobs", self.web(), body=self.image_job())
            statuses.append(status)
        self.assertEqual(statuses, [201, 201, 429])
        status, _ = await self.call("POST", "/api/jobs", self.web("someone.else@example.com"), body=self.image_job())
        self.assertEqual(status, 201)
        status, _ = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job())
        self.assertEqual(status, 201)
        self.assertEqual(len(self.queue.jobs()), 4)

    async def test_at_most_two_renders_run_at_once(self):
        lock = threading.Lock()
        running, peak = 0, 0

        def slow_render(kind, **content):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.2)
            with lock:
                running -= 1
            return RENDERED

        with mock.patch.object(http_api, "render", side_effect=slow_render):
            results = await asyncio.gather(*(
                self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job()) for _ in range(6)
            ))
        self.assertEqual([status for status, _ in results], [201] * 6)
        self.assertEqual(peak, 2)

    async def test_rate_limit_forgets_senders_once_their_window_passes(self):
        api = next(route.handler.__self__ for route in self.app.router.routes()
                   if getattr(route.handler, "__name__", "") == "post_job")
        await self.call("POST", "/api/jobs", self.web(), body=self.image_job())
        self.assertEqual(list(api.web_jobs), [SENDER_EMAIL])
        later = time.monotonic() + http_api.RATE_WINDOW_SECONDS + 1
        with mock.patch.object(http_api.time, "monotonic", return_value=later):
            await self.call("POST", "/api/jobs", self.web("someone.else@example.com"), body=self.image_job())
        self.assertEqual(list(api.web_jobs), ["someone.else@example.com"])

    async def test_a_new_job_wakes_the_printer_delivery(self):
        wake = self.hub._wakes["home"]
        wake.clear()
        await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job())
        self.assertTrue(wake.is_set())


class CrossSiteTest(ServerTestCase):
    """A POST that carries only the browser's Access cookie must be a same-site JSON request."""

    def post_routes(self) -> list[tuple[str, dict, int]]:
        """Each POST route with a valid body and the status a bearer caller gets."""
        queued, finished = self.add_job("home"), self.add_job("home")
        self.queue.cancel(finished.id)
        return [
            ("/api/jobs", self.image_job(), 201),
            (f"/api/jobs/{queued.id}/cancel", {}, 200),
            (f"/api/jobs/{finished.id}/reprint", {}, 201),
            ("/api/printers/home/clear", {}, 200),
            ("/api/printers/home/move", {"to": "office"}, 200),
        ]

    async def post(self, path: str, headers: dict, content_type: str, body: dict) -> int:
        if content_type == "application/x-www-form-urlencoded":
            data = "&".join(f"{key}={value}" for key, value in body.items()).encode()
        else:
            data = json.dumps(body).encode()
        status, _ = await self.call("POST", path, {**headers, "Content-Type": content_type}, data=data)
        return status

    async def test_an_access_caller_post_that_is_not_json_is_refused_on_every_route(self):
        for content_type in ("application/x-www-form-urlencoded", "text/plain", "multipart/form-data"):
            for path, body, _ in self.post_routes():
                with self.subTest(content_type=content_type, path=path):
                    self.assertEqual(await self.post(path, self.web(ADMIN_EMAIL), content_type, body), 403)
        jobs = self.queue.jobs()
        self.assertEqual(len(jobs), 6)
        self.assertEqual(sorted(job.status for job in jobs), ["cancelled"] * 3 + ["queued"] * 3)

    async def test_an_access_caller_post_from_another_site_is_refused(self):
        for site, expected in (("cross-site", 403), ("same-site", 403), ("same-origin", 201), ("none", 201)):
            with self.subTest(site=site):
                headers = {**self.web(), "Sec-Fetch-Site": site}
                status, _ = await self.call("POST", "/api/jobs", headers, body=self.image_job())
                self.assertEqual(status, expected)

    async def test_the_same_text_plain_requests_work_with_a_bearer_token(self):
        for path, body, expected in self.post_routes():
            with self.subTest(path=path):
                self.assertEqual(await self.post(path, self.bearer(ADMIN_TOKEN), "text/plain", body), expected)

    async def test_a_bodyless_json_post_from_an_admin_email_works(self):
        job = self.add_job()
        status, _ = await self.call("POST", f"/api/jobs/{job.id}/cancel",
                                    {**self.web(ADMIN_EMAIL), "Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(self.queue.job(job.id).status, "cancelled")


class AdminTest(ServerTestCase):
    def setUp(self):
        self.admin = self.bearer(ADMIN_TOKEN)

    async def test_list_jobs_filters_by_printer_and_status_newest_first(self):
        first, second, third = self.add_job("home"), self.add_job("office"), self.add_job("home")
        self.queue.cancel(third.id)
        status, body = await self.call("GET", "/api/jobs", self.admin)
        self.assertEqual([job["id"] for job in body["jobs"]], [third.id, second.id, first.id])
        self.assertNotIn("events", body["jobs"][0])
        _, body = await self.call("GET", "/api/jobs?printer=home&status=queued", self.admin)
        self.assertEqual([job["id"] for job in body["jobs"]], [first.id])
        _, body = await self.call("GET", "/api/jobs?limit=1", self.admin)
        self.assertEqual([job["id"] for job in body["jobs"]], [third.id])
        for query in ("status=lost", "limit=0", "limit=abc", "limit=1001"):
            with self.subTest(query=query):
                status, _ = await self.call("GET", f"/api/jobs?{query}", self.admin)
                self.assertEqual(status, 400)

    async def test_get_job_returns_its_events(self):
        job = self.add_job()
        status, body = await self.call("GET", f"/api/jobs/{job.id}", self.admin)
        self.assertEqual(status, 200)
        self.assertEqual([event["event"] for event in body["events"]], ["received", "rendered"])
        self.assertEqual(body["events"][0]["job_id"], job.id)
        status, _ = await self.call("GET", "/api/jobs/00000000", self.admin)
        self.assertEqual(status, 404)

    async def test_job_image_is_the_stored_png_until_pruned(self):
        job = self.add_job()
        response = await self.client.get(f"/api/jobs/{job.id}/image", headers=self.admin)
        self.assertEqual((response.status, response.content_type), (200, "image/png"))
        self.assertEqual(await response.read(), RENDERED.png)
        self.queue.prune(now=time.time() + 31 * 86400)
        status, _ = await self.call("GET", f"/api/jobs/{job.id}/image", self.admin)
        self.assertEqual(status, 404)

    async def test_cancel_a_queued_job_then_409_once_final(self):
        job = self.add_job()
        status, body = await self.call("POST", f"/api/jobs/{job.id}/cancel", self.admin)
        self.assertEqual((status, body["status"]), (200, "cancelled"))
        status, _ = await self.call("POST", f"/api/jobs/{job.id}/cancel", self.admin)
        self.assertEqual(status, 409)
        status, _ = await self.call("POST", "/api/jobs/00000000/cancel", self.admin)
        self.assertEqual(status, 404)
        self.assertEventsMatchStatus(job.id)

    async def test_reprint_queues_a_copy_from_the_stored_png_as_the_admin(self):
        job = self.add_job("home")
        status, _ = await self.call("POST", f"/api/jobs/{job.id}/reprint", self.admin)
        self.assertEqual(status, 409)
        self.queue.take("home")
        self.queue.confirm(job.id)

        status, copy = await self.call("POST", f"/api/jobs/{job.id}/reprint", self.admin, body={"printer": "office"})
        self.assertEqual(status, 201, copy)
        self.assertEqual((copy["printer"], copy["source"], copy["ingress"]), ("office", "admin", "cli"))
        self.assertEqual(self.queue.take("office").data, RENDERED.escpos)

        status, copy = await self.call("POST", f"/api/jobs/{job.id}/reprint", self.web(ADMIN_EMAIL), body={})
        self.assertEqual((status, copy["printer"], copy["source"], copy["ingress"]),
                         (201, "home", ADMIN_EMAIL, "admin-web"))
        self.assertIn("reprinted", [event.event for event in self.queue.job(job.id).events])

        status, _ = await self.call("POST", f"/api/jobs/{job.id}/reprint", self.admin, body={"printer": "garage"})
        self.assertEqual(status, 404)
        status, _ = await self.call("POST", "/api/jobs/00000000/reprint", self.admin)
        self.assertEqual(status, 404)
        self.queue.prune(now=time.time() + 31 * 86400)
        status, _ = await self.call("POST", f"/api/jobs/{job.id}/reprint", self.admin)
        self.assertEqual(status, 404)

    async def test_clear_cancels_only_that_printers_queue(self):
        home, office = self.add_job("home"), self.add_job("office")
        status, body = await self.call("POST", "/api/printers/home/clear", self.admin)
        self.assertEqual((status, body), (200, {"cancelled": 1}))
        self.assertEqual(self.queue.job(home.id).status, "cancelled")
        self.assertEqual(self.queue.job(office.id).status, "queued")
        status, _ = await self.call("POST", "/api/printers/garage/clear", self.admin)
        self.assertEqual(status, 404)

    async def test_move_sends_the_queued_jobs_to_another_printer(self):
        job = self.add_job("home")
        status, body = await self.call("POST", "/api/printers/home/move", self.admin, body={"to": "office"})
        self.assertEqual((status, body), (200, {"moved": 1}))
        self.assertEqual(self.queue.job(job.id).printer, "office")
        cases = [({"to": "home"}, 400, "home"), ({}, 400, "home"), ({"to": "garage"}, 404, "home"),
                 ({"to": "office"}, 404, "garage")]
        for body, expected, source in cases:
            with self.subTest(body=body, source=source):
                status, _ = await self.call("POST", f"/api/printers/{source}/move", self.admin, body=body)
                self.assertEqual(status, expected)

    async def test_printers_merges_config_state_and_counts_including_printers_never_seen(self):
        self.add_job("home")
        self.add_job("home")
        self.queue.update_printer_state("home", latency_ms=12.5, client_version="python/1", route="tunnel")
        status, body = await self.call("GET", "/api/printers", self.admin)
        self.assertEqual(status, 200)
        printers = {printer["id"]: printer for printer in body["printers"]}
        self.assertEqual(set(printers), {"home", "office"})
        home, office = printers["home"], printers["office"]
        self.assertEqual((home["name"], home["place"], home["public"]), ("Home", "Home office", True))
        self.assertEqual((home["latency_ms"], home["client_version"], home["route"]), (12.5, "python/1", "tunnel"))
        self.assertEqual((home["queued"], home["printed_today"], home["online"], home["current_job"]),
                         (2, 0, False, None))
        self.assertEqual((office["queued"], office["online"], office["last_seen"], office["public"]),
                         (0, False, None, False))
        for printer in printers.values():
            self.assertNotIn("token", json.dumps(printer))

    async def test_stats_fill_hourly_with_zeros_for_printers_without_jobs(self):
        job = self.add_job("home")
        self.queue.take("home")
        self.queue.confirm(job.id)
        status, body = await self.call("GET", "/api/stats", self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(body["printed_today"], 1)
        self.assertEqual(body["hourly"]["office"], [0] * 24)
        self.assertEqual(sum(body["hourly"]["home"]), 1)
        self.assertEqual(body["paper_today_mm"], RENDERED.height / 8)

    async def test_stats_hourly_lists_only_configured_printers(self):
        job = self.add_job("garage")
        self.queue.take("garage")
        self.queue.confirm(job.id)
        status, body = await self.call("GET", "/api/stats", self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(set(body["hourly"]), {"home", "office"})


class AdminViewsTest(ServerTestCase):
    def setUp(self):
        self.admin = self.bearer(ADMIN_TOKEN)

    def add(self, source: str, ingress: str, title: str, created_at: float):
        return self.queue.add(
            "home", RENDERED.escpos, kind="image", title=title, source=source, ingress=ingress, png=RENDERED.png,
            width=RENDERED.width, height=RENDERED.height, render_ms=RENDERED.render_ms, now=created_at,
        )

    async def test_clients_lists_configured_clients_and_web_senders_with_todays_jobs_and_last_job(self):
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today = max(midnight + 60, time.time() - 600)
        self.add("morning-brief", "api", "Yesterday's brief", midnight - 3600)
        self.add("morning-brief", "api", "Brief", today)
        newest = self.add("morning-brief", "api", "Second brief", today + 5)
        sender = self.add(SENDER_EMAIL, "web", "Hi from Lisbon", today + 10)
        self.add("admin", "cli", "Admin test print", today + 20)
        self.add(ADMIN_EMAIL, "admin-web", "Reprint", today + 30)
        self.add("removed-client", "api", "From a client no longer in the config", today + 40)

        status, body = await self.call("GET", "/api/clients", self.admin)

        self.assertEqual(status, 200)
        self.assertEqual(body["clients"], [
            {"id": "morning-brief", "kind": "client", "jobs_today": 2, "last_job": {
                "id": newest.id, "title": "Second brief", "kind": "image", "printer": "home",
                "created_at": newest.created_at}},
            {"id": SENDER_EMAIL, "kind": "web", "jobs_today": 1, "last_job": {
                "id": sender.id, "title": "Hi from Lisbon", "kind": "image", "printer": "home",
                "created_at": sender.created_at}},
        ])

    async def test_clients_shows_a_configured_client_without_jobs(self):
        status, body = await self.call("GET", "/api/clients", self.admin)
        self.assertEqual((status, body), (200, {"clients": [
            {"id": "morning-brief", "kind": "client", "jobs_today": 0, "last_job": None}]}))

    async def test_server_reports_version_uptime_and_the_renders_in_progress(self):
        started = threading.Event()
        release = threading.Event()

        def slow_render(kind, **content):
            started.set()
            release.wait(5)
            return RENDERED

        status, body = await self.call("GET", "/api/server", self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"version", "started_at", "uptime_seconds", "renders_in_progress"})
        project = tomllib.loads((_TESTS.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(body["version"], project["version"])
        self.assertGreaterEqual(body["uptime_seconds"], 0)
        self.assertLessEqual(body["started_at"], time.time())
        self.assertEqual(body["renders_in_progress"], 0)

        with mock.patch.object(http_api, "render", side_effect=slow_render):
            posting = asyncio.ensure_future(
                self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job()))
            await asyncio.to_thread(started.wait, 5)
            _, during = await self.call("GET", "/api/server", self.admin)
            release.set()
            status, _ = await posting
        self.assertEqual((during["renders_in_progress"], status), (1, 201))
        _, after = await self.call("GET", "/api/server", self.admin)
        self.assertEqual(after["renders_in_progress"], 0)

    async def test_a_failed_render_frees_its_count(self):
        with mock.patch.object(http_api, "render", side_effect=RuntimeError("boom")):
            status, _ = await self.call("POST", "/api/jobs", self.bearer(CLIENT_TOKEN), body=self.image_job())
        self.assertEqual(status, 500)
        _, body = await self.call("GET", "/api/server", self.admin)
        self.assertEqual(body["renders_in_progress"], 0)
        self.assertIn("rendering a image job for morning-brief failed", self.logs.text())


if __name__ == "__main__":
    unittest.main()
