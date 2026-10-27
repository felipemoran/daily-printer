import asyncio
import base64
import email
import functools
import json
import re
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image
from playwright.sync_api import sync_playwright

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

import http_api  # noqa: E402
import job_artifacts  # noqa: E402
import render_job  # noqa: E402
from http_api import create_app  # noqa: E402
from job_artifacts import artifacts_root, dist_sha256  # noqa: E402
from printer import PRINT_WIDTH_DOTS  # noqa: E402
from raster_capture import snapshot_mhtml  # noqa: E402
from render_job import DIST_DIR, render  # noqa: E402
from ticket_templates import launch_browser, open_render_page, render_template  # noqa: E402
from test_http_api import ADMIN_TOKEN, PHOTO, SAMPLE_PAYLOAD, ServerTestCase  # noqa: E402

SAMPLES = _TESTS.parent / "samples" / "templates"
TICKET = json.loads((SAMPLES / "ticket.json").read_text(encoding="utf-8"))
BUILD = json.loads((SAMPLES / "build.json").read_text(encoding="utf-8"))
SPRINT = json.loads((SAMPLES / "sprint.json").read_text(encoding="utf-8"))
PAGE_FILES = {"request.json", "page.mhtml", "screenshot.png", "print.png", "job.escpos", "meta.json"}
CASES = {
    "receipt": ("receipt", {"payload": SAMPLE_PAYLOAD}, PAGE_FILES),
    "template": ("template", {"payload": TICKET}, PAGE_FILES),
    "landscape template": ("template", {"payload": SPRINT}, PAGE_FILES),
    "text": ("text", {"payload": BUILD}, PAGE_FILES),
    "image": ("image", {"image": PHOTO}, {"source.png", "print.png", "job.escpos", "meta.json"}),
}
FONT_URL = re.compile(rb'url\("data:font/woff2;base64,([A-Za-z0-9+/=]+)"\)')


def _nested(depth: int) -> dict:
    node: dict = {}
    for _ in range(depth - 1):
        node = {"x": node}
    return node


def _receipt_body(depth: int) -> bytes:
    """A receipt request whose payload nests ``depth`` objects deep."""
    head = '{"printer":"home","kind":"receipt","title":"deep","payload":'
    return (head + '{"x":' * (depth - 1) + "{}" + "}" * (depth - 1) + "}").encode()


def _request(kind: str, content: dict) -> dict:
    body = {"printer": "home", "kind": kind, "title": kind}
    if "image" in content:
        body["image"] = base64.b64encode(content["image"]).decode()
    else:
        body["payload"] = content["payload"]
    return body


@functools.cache
def _renders() -> dict:
    return {name: render(kind, **content) for name, (kind, content, _) in CASES.items()}


class ArtifactTestCase(ServerTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.rendered = await asyncio.to_thread(_renders)
        self.admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        self.root = artifacts_root(self.config.database)

    async def send(self, name: str, *, payload: dict | None = None) -> dict:
        """Post the case through the real route, with its render taken from the class's real renders."""
        kind, content, _ = CASES[name]
        body = _request(kind, content if payload is None else {"payload": payload})
        with mock.patch.object(http_api, "render", return_value=self.rendered[name]):
            status, job = await self.call("POST", "/api/jobs", self.admin, body=body)
        self.assertEqual(status, 201, job)
        return job

    def file(self, job_id: str, name: str) -> bytes:
        return (self.root / job_id / name).read_bytes()


class IntakeTest(ArtifactTestCase):
    async def test_each_kind_keeps_its_files_and_the_bytes_it_queued_and_sent(self):
        for name, (kind, _, expected) in CASES.items():
            with self.subTest(name):
                job = await self.send(name)
                self.assertEqual({path.name for path in (self.root / job["id"]).iterdir()}, expected)
                rendered = self.rendered[name]
                self.assertEqual(self.file(job["id"], "print.png"), rendered.png)
                self.assertEqual(self.file(job["id"], "job.escpos"), rendered.escpos)
                sent = self.queue.take("home")
                self.assertEqual(sent.id, job["id"])
                self.assertEqual(sent.data, self.file(job["id"], "job.escpos"))
                self.queue.confirm(sent.id)
                if kind == "image":
                    self.assertEqual(self.file(job["id"], "source.png"), PHOTO)

    async def post_raw(self, body: bytes, *, name: str = "receipt") -> tuple[int, object]:
        headers = {**self.admin, "Content-Type": "application/json"}
        with mock.patch.object(http_api, "render", return_value=self.rendered[name]):
            return await self.call("POST", "/api/jobs", headers, data=body)

    async def test_request_json_is_the_request_body_byte_for_byte(self):
        envelope = json.dumps(TICKET)[1:-1]
        body = ('{ "printer" : "home",\n\t"kind":"template", "title": "Caf\u00e9 \u2713",\n'
                '  "payload": {' + envelope + ', "note": "Caf\u00e9 \\u00e9 \\ud800 \\ud83d\\udda8",'
                ' "big": 1e15, "huge": 1e400, "tiny": -0.0, "list": [ 1 , 2 ] } }\n').encode()
        status, job = await self.post_raw(body, name="template")
        self.assertEqual(status, 201, job)
        self.assertEqual(self.file(job["id"], "request.json"), body)

    async def test_a_receipt_with_a_lone_surrogate_renders_and_is_stored_as_sent(self):
        payload = json.dumps(SAMPLE_PAYLOAD)
        body = ('{"printer": "home", "kind": "receipt", "payload": ' + payload.replace(
            '"blocks": [', '"note": "\\ud800", "blocks": [', 1) + "}").encode()
        self.assertIn(b'"\\ud800"', body)
        status, job = await self.call("POST", "/api/jobs", {**self.admin, "Content-Type": "application/json"}, data=body)
        self.assertEqual(status, 201, job)
        self.assertEqual(self.file(job["id"], "request.json"), body)

    async def test_a_deeply_nested_payload_is_stored_no_larger_than_its_request(self):
        body = json.dumps({"printer": "home", "kind": "receipt", "title": "deep", "payload": _nested(900)}).encode()
        status, job = await self.post_raw(body)
        self.assertEqual(status, 201, job)
        self.assertEqual(self.file(job["id"], "request.json"), body)

    async def test_the_deepest_body_the_parser_accepts_is_stored_or_refused_cleanly(self):
        low, high, deepest = 1, 100_000, None
        while low < high:
            middle = (low + high + 1) // 2
            status, job = await self.post_raw(_receipt_body(middle))
            if status == 400:
                self.assertEqual(job, {"error": "the body is not valid JSON"})
                high = middle - 1
            else:
                low, deepest = middle, (status, job)
        self.assertGreater(low, 900)
        status, job = deepest
        self.assertIn((status, job if status == 500 else None),
                      [(201, None), (500, {"error": "saving the job failed on the server"})])
        folders = {path.name for path in self.root.iterdir()}
        self.assertEqual(folders, {listed.id for listed in self.queue.jobs()})
        self.assertFalse([name for name in folders if name.startswith(".tmp-")])

    async def test_any_failure_while_building_the_files_is_the_clean_500(self):
        with mock.patch.object(http_api, "job_files", side_effect=RecursionError("maximum recursion depth")):
            status, body = await self.post_raw(json.dumps(_request("receipt", {"payload": SAMPLE_PAYLOAD})).encode())
        self.assertEqual((status, body), (500, {"error": "saving the job failed on the server"}))
        self.assertEqual(list(self.root.iterdir()) if self.root.exists() else [], [])
        self.assertEqual(self.queue.jobs(), [])

    async def test_job_folders_are_private_to_the_server_user(self):
        for name in ("receipt", "image"):
            with self.subTest(name):
                job = await self.send(name)
                self.assertEqual((self.root / job["id"]).stat().st_mode & 0o777, 0o700)

    async def test_an_id_that_climbs_out_of_the_folder_is_an_unknown_job(self):
        await self.send("image")
        for method, path in (("GET", "/api/jobs/..%2F..%2Fdata/image"), ("POST", "/api/jobs/..%2Fartifacts/reprint"),
                             ("GET", "/api/jobs/..%2F/image"), ("POST", "/api/jobs/..%2F/reprint")):
            with self.subTest(path):
                status, body = await self.call(method, path, self.admin)
                self.assertEqual((status, body), (404, {"error": "unknown job"}))

    async def test_meta_json_describes_the_render(self):
        job = await self.send("text")
        meta = json.loads(self.file(job["id"], "meta.json"))
        rendered = self.rendered["text"]
        self.assertEqual(meta, {
            "kind": "text", "template": "build", "created_at": job["created_at"], "width": rendered.width,
            "height": rendered.height, "render_ms": rendered.render_ms, "web_dist_sha256": dist_sha256(),
        })
        self.assertRegex(meta["web_dist_sha256"], "^[0-9a-f]{64}$")

    async def test_web_dist_sha256_follows_a_rebuild_while_the_server_runs(self):
        dist = self.tmp / "dist"
        dist.mkdir()
        (dist / "render.html").write_text("first build")
        with mock.patch.object(job_artifacts, "DIST_DIR", dist):
            first = json.loads(self.file((await self.send("image"))["id"], "meta.json"))["web_dist_sha256"]
            (dist / "render.html").write_text("second build")
            second = json.loads(self.file((await self.send("image"))["id"], "meta.json"))["web_dist_sha256"]
        self.assertRegex(first, "^[0-9a-f]{64}$")
        self.assertNotEqual(first, second)

    async def test_page_mhtml_is_an_mhtml_archive_with_the_fonts_the_page_used(self):
        fonts = {path.read_bytes() for path in (DIST_DIR / "fonts").rglob("*.woff2")}
        archives = {}
        # The receipt app draws in system fonts (Tahoma, Verdana), which no archive carries.
        for name, web_fonts in (("receipt", False), ("template", True), ("text", True)):
            with self.subTest(name):
                job = await self.send(name)
                archive = self.root / job["id"] / "page.mhtml"
                message = email.message_from_bytes(archive.read_bytes())
                self.assertEqual(message.get_content_type(), "multipart/related")
                parts = message.get_payload()
                self.assertEqual(parts[0].get_content_type(), "text/html")
                styles = b"".join(part.get_payload(decode=True) for part in parts
                                  if part.get_content_type() == "text/css")
                embedded = [base64.b64decode(match) for match in FONT_URL.findall(styles)]
                self.assertEqual(bool(embedded), web_fonts)
                self.assertTrue(all(font in fonts for font in embedded), "a font that is not in web/dist")
                if web_fonts:
                    archives[name] = archive
        # Offline, the faces with a data: URL load, so the archive shows the ticket in its own fonts.
        loaded = await asyncio.to_thread(_offline_fonts, list(archives.values()))
        for name, families in zip(archives, loaded):
            with self.subTest(name):
                self.assertTrue(families)

    async def test_screenshot_png_is_the_capture_before_any_treatment(self):
        for name in ("receipt", "template", "landscape template"):
            with self.subTest(name):
                job = await self.send(name)
                screenshot = self.file(job["id"], "screenshot.png")
                self.assertNotEqual(screenshot, self.file(job["id"], "print.png"))
                with Image.open(self.root / job["id"] / "screenshot.png") as image:
                    self.assertNotEqual(image.mode, "1")
                    across, along = (image.height, image.width) if name.startswith("landscape") else image.size
                self.assertEqual((across, along), (PRINT_WIDTH_DOTS, job["height"]))
        with Image.open(self.root / job["id"] / "screenshot.png") as image:
            self.assertGreater(image.width, image.height)

    async def test_a_failed_artifact_write_is_a_500_that_leaves_no_folder_and_no_job(self):
        write_bytes = Path.write_bytes

        def failing(path, data):
            if path.name == "job.escpos":
                raise OSError(28, "No space left on device")
            return write_bytes(path, data)

        with mock.patch.object(Path, "write_bytes", failing), \
                mock.patch.object(http_api, "render", return_value=self.rendered["image"]):
            status, body = await self.call("POST", "/api/jobs", self.admin, body=_request("image", {"image": PHOTO}))
        self.assertEqual((status, body), (500, {"error": "saving the job failed on the server"}))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.queue.jobs(), [])

    async def test_a_failed_rename_rolls_the_job_back_and_leaves_no_folder(self):
        with mock.patch.object(Path, "rename", side_effect=OSError(5, "Input/output error")):
            status, _ = await self.call("POST", "/api/jobs", self.admin, body=_request("image", {"image": PHOTO}))
        self.assertEqual(status, 500)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.queue.jobs(), [])


class ReprintTest(ArtifactTestCase):
    async def finished(self, name: str, **payload) -> dict:
        job = await self.send(name, **payload)
        self.queue.cancel(job["id"])
        return job

    async def test_reprint_copies_the_folder_sends_the_same_bytes_and_records_reprint_of(self):
        for name, (kind, _, _) in CASES.items():
            with self.subTest(name):
                job = await self.finished(name)
                status, copy = await self.call("POST", f"/api/jobs/{job['id']}/reprint", self.admin)
                self.assertEqual(status, 201, copy)
                self.assertEqual(copy["kind"], kind)
                source, target = self.root / job["id"], self.root / copy["id"]
                names = sorted(path.name for path in source.iterdir())
                self.assertEqual(sorted(path.name for path in target.iterdir()), names)
                for file in names:
                    if file != "meta.json":
                        self.assertEqual((target / file).read_bytes(), (source / file).read_bytes(), file)
                meta = json.loads((source / "meta.json").read_bytes())
                self.assertEqual(json.loads((target / "meta.json").read_bytes()),
                                 {**meta, "created_at": copy["created_at"], "reprint_of": job["id"]})
                self.assertEqual(self.queue.take("home").data, (source / "job.escpos").read_bytes())
                self.queue.cancel(copy["id"])

    async def test_a_reprint_holds_its_own_copies_of_the_files(self):
        job = await self.finished("text")
        status, copy = await self.call("POST", f"/api/jobs/{job['id']}/reprint", self.admin)
        self.assertEqual(status, 201, copy)
        for file in (self.root / copy["id"]).iterdir():
            with self.subTest(file.name):
                self.assertEqual(file.stat().st_nlink, 1)
        (self.root / copy["id"] / "print.png").write_bytes(b"edited")
        self.assertEqual(self.file(job["id"], "print.png"), self.rendered["text"].png)

    async def test_a_job_without_its_folder_cannot_be_reprinted(self):
        job = await self.finished("image")
        shutil.rmtree(self.root / job["id"])
        status, body = await self.call("POST", f"/api/jobs/{job['id']}/reprint", self.admin)
        self.assertEqual((status, body), (409, {"error": f"job {job['id']} has no artifact folder with its printer "
                                                         f"bytes, so it cannot be reprinted"}))
        self.assertEqual([listed.id for listed in self.queue.jobs()], [job["id"]])

    async def test_a_later_change_cannot_alter_a_past_ticket(self):
        body = _request("text", {"payload": BUILD})
        status, past = await self.call("POST", "/api/jobs", self.admin, body=body)
        self.assertEqual(status, 201, past)
        printed = self.file(past["id"], "print.png"), self.file(past["id"], "job.escpos")
        self.queue.cancel(past["id"])

        changed = Image.new("1", (PRINT_WIDTH_DOTS, 40), 0)
        with mock.patch.object(render_job, "bitmap_from_capture", return_value=changed), \
                mock.patch.object(render_job, "render_text", return_value=b"CHANGED\n"):
            status, now = await self.call("POST", "/api/jobs", self.admin, body=body)
            self.assertEqual(status, 201, now)
            self.assertNotEqual((self.file(now["id"], "print.png"), self.file(now["id"], "job.escpos")), printed)

            response = await self.client.get(f"/api/jobs/{past['id']}/image", headers=self.admin)
            self.assertEqual(await response.read(), printed[0])
            status, copy = await self.call("POST", f"/api/jobs/{past['id']}/reprint", self.admin)
            self.assertEqual(status, 201, copy)
        self.queue.cancel(now["id"])
        self.assertEqual(self.queue.take("home").data, printed[1])
        self.assertEqual((self.file(copy["id"], "print.png"), self.file(copy["id"], "job.escpos")), printed)


class SweepTest(ArtifactTestCase):
    async def test_stale_staging_folders_are_deleted_at_start_and_job_folders_kept(self):
        job = await self.send("image")
        stale = self.root / ".tmp-k3j2h1"
        stale.mkdir()
        (stale / "print.png").write_bytes(b"half")
        app = create_app(self.config, self.queue)
        client = TestClient(TestServer(app))
        await client.start_server()
        await client.close()
        self.assertEqual([path.name for path in self.root.iterdir()], [job["id"]])


class FontSnapshotTest(unittest.TestCase):
    def test_a_font_that_fails_to_load_again_fails_the_snapshot_with_its_url(self):
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                page = open_render_page(browser)
                render_template(page, TICKET)
                page.route("**/fonts/**", lambda route: route.fulfill(status=404, body="Not Found"))
                with self.assertRaisesRegex(RuntimeError, r"fonts/.*\.woff2 answered HTTP 404"):
                    snapshot_mhtml(page)
            finally:
                browser.close()


def _offline_fonts(archives: list[Path]) -> list[list[str]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_context(offline=True).new_page()
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:")
                       else route.abort())
            result = []
            for archive in archives:
                page.goto(archive.as_uri())
                result.append(page.evaluate("""async () => {
                    await document.fonts.ready;
                    return [...document.fonts].filter((font) => font.status === 'loaded').map((font) => font.family);
                }"""))
            return result
        finally:
            browser.close()
