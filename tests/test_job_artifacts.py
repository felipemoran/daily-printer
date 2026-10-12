import asyncio
import base64
import email
import functools
import json
import re
import sys
from pathlib import Path
from unittest import mock

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image
from playwright.sync_api import sync_playwright

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

import http_api  # noqa: E402
from http_api import create_app  # noqa: E402
from job_artifacts import artifacts_root, dist_sha256  # noqa: E402
from printer import PRINT_WIDTH_DOTS  # noqa: E402
from render_job import DIST_DIR, render  # noqa: E402
from test_http_api import ADMIN_TOKEN, PHOTO, SAMPLE_PAYLOAD, ServerTestCase  # noqa: E402

SAMPLES = _TESTS.parent / "samples" / "templates"
TICKET = json.loads((SAMPLES / "ticket.json").read_text(encoding="utf-8"))
BUILD = json.loads((SAMPLES / "build.json").read_text(encoding="utf-8"))
SPRINT = json.loads((SAMPLES / "sprint.json").read_text(encoding="utf-8"))
PAGE_FILES = {"payload.json", "page.mhtml", "screenshot.png", "print.png", "job.escpos", "meta.json"}
CASES = {
    "receipt": ("receipt", {"payload": SAMPLE_PAYLOAD}, PAGE_FILES),
    "template": ("template", {"payload": TICKET}, PAGE_FILES),
    "landscape template": ("template", {"payload": SPRINT}, PAGE_FILES),
    "text": ("text", {"payload": BUILD}, PAGE_FILES),
    "image": ("image", {"image": PHOTO}, {"source.png", "print.png", "job.escpos", "meta.json"}),
}
FONT_URL = re.compile(rb'url\("data:font/woff2;base64,([A-Za-z0-9+/=]+)"\)')


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

    async def test_payload_json_round_trips_the_input(self):
        payload = {**TICKET, "data": {**TICKET["data"], "note": "Caf\u00e9 \u2713 \u2028 \"q\" \\ \U0001f5a8",
                                      "ratio": 1.0, "big": 2**63, "small": 1e-300, "empty": {}, "list": [None, True]}}
        job = await self.send("template", payload=payload)
        stored = self.file(job["id"], "payload.json")
        self.assertEqual(json.loads(stored), payload)
        self.assertEqual(json.dumps(json.loads(stored), sort_keys=True), json.dumps(payload, sort_keys=True))

    async def test_meta_json_describes_the_render(self):
        job = await self.send("text")
        meta = json.loads(self.file(job["id"], "meta.json"))
        rendered = self.rendered["text"]
        self.assertEqual(meta, {
            "kind": "text", "template": "build", "created_at": job["created_at"], "width": rendered.width,
            "height": rendered.height, "render_ms": rendered.render_ms, "web_dist_sha256": dist_sha256(),
        })
        self.assertRegex(meta["web_dist_sha256"], "^[0-9a-f]{64}$")

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
