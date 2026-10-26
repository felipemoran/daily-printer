"""Chromium on another origin calls the server through a stand-in for Cloudflare Access."""

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
from multidict import CIMultiDict
from playwright.async_api import async_playwright

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

from access_auth import HEADER  # noqa: E402
from test_http_api import ADMIN_EMAIL, HOME_TOKEN, SENDER_EMAIL, ServerTestCase  # noqa: E402
from test_template_recipe import MADALENA  # noqa: E402
from tests.web_build import build_web  # noqa: E402

PAGE = b"<!doctype html><meta charset=utf-8><title>mise en place</title>"
TEST_PAGE = json.loads((_TESTS.parent / "samples" / "templates" / "test-page.json").read_text(encoding="utf-8"))
HOP_BY_HOP = {"host", "connection", "keep-alive", "transfer-encoding", "content-length", "accept-encoding",
              "content-encoding", "date", "server"}
FETCH_JS = """async ([url, init]) => {
  try {
    const response = await fetch(url, {credentials: "include", ...init});
    return {status: response.status, body: await response.text()};
  } catch (error) {
    return {error: error.name};
  }
}"""


def setUpModule():
    build_web()


def template_job(payload: dict, **extra) -> dict:
    return {"printer": "home", "kind": "template", "title": "Recipe", "payload": payload, **extra}


class CrossOriginBrowserTest(ServerTestCase):
    """The page origin is allowed; the same page on localhost is not. No real printer is involved."""

    async def asyncSetUp(self) -> None:
        async def page(_: web.Request) -> web.Response:
            return web.Response(body=PAGE, content_type="text/html")

        pages = web.Application()
        pages.router.add_get("/", page)
        page_server = TestServer(pages, host="127.0.0.1")
        await page_server.start_server()
        self.addAsyncCleanup(page_server.close)
        self.allowed_page = f"http://127.0.0.1:{page_server.port}"
        self.other_page = f"http://localhost:{page_server.port}"
        self.allowed_origins = (self.allowed_page,)
        await super().asyncSetUp()

        self.upstream = str(self.client.make_url("")).rstrip("/")
        self.proxy_email = SENDER_EMAIL
        self.forwarded: list[tuple[str, str, int]] = []
        self.session = ClientSession(auto_decompress=False)
        self.addAsyncCleanup(self.session.close)
        proxy = web.Application()
        proxy.router.add_route("*", "/{tail:.*}", self.forward)
        proxy_server = TestServer(proxy, host="127.0.0.1")
        await proxy_server.start_server()
        self.addAsyncCleanup(proxy_server.close)
        self.proxy = f"http://127.0.0.1:{proxy_server.port}"

        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.addAsyncCleanup(self.browser.close)

    async def forward(self, request: web.Request) -> web.Response:
        """Access: OPTIONS goes to the origin untouched; every other request gets the sender's assertion."""
        headers = CIMultiDict((k, v) for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP)
        if request.method != "OPTIONS":
            headers[HEADER] = self.web(self.proxy_email)[HEADER]
        body = await request.read()
        async with self.session.request(request.method, self.upstream + request.path_qs, headers=headers,
                                        data=body or None, allow_redirects=False) as got:
            raw = await got.read()
            self.forwarded.append((request.method, request.path, got.status))
            kept = CIMultiDict((k, v) for k, v in got.headers.items() if k.lower() not in HOP_BY_HOP)
            return web.Response(status=got.status, body=raw, headers=kept)

    async def fetch(self, page_origin: str, path: str, job: dict | None = None) -> dict:
        context = await self.browser.new_context()
        self.addAsyncCleanup(context.close)
        page = await context.new_page()
        await page.goto(page_origin + "/")
        init = {} if job is None else {
            "method": "POST", "headers": {"Content-Type": "application/json"}, "body": json.dumps(job)}
        return await page.evaluate(FETCH_JS, [self.proxy + path, init])

    async def test_an_allowed_origin_reads_api_me_with_the_public_printer_online(self):
        device = {**self.bearer(HOME_TOKEN), "X-Device-Version": "python/1"}
        ws = await self.client.ws_connect("/device", headers=device)
        self.addAsyncCleanup(ws.close)
        deadline = time.monotonic() + 5
        while not self.hub.online("home"):
            self.assertLess(time.monotonic(), deadline, "the device never came online")
            await asyncio.sleep(0.01)
        got = await self.fetch(self.allowed_page, "/api/me")
        self.assertEqual(got.get("status"), 200, got)
        printers = {printer["id"]: printer for printer in json.loads(got["body"])["printers"]}
        self.assertEqual(list(printers), ["home"])
        self.assertIs(printers["home"]["online"], True)

    async def test_an_allowed_origin_posts_a_json_template_job_and_reads_the_201(self):
        got = await self.fetch(self.allowed_page, "/api/jobs", template_job(TEST_PAGE))
        self.assertEqual(got.get("status"), 201, got)
        self.assertEqual(json.loads(got["body"])["status"], "queued")
        self.assertEqual([method for method, path, _ in self.forwarded if path == "/api/jobs"], ["OPTIONS", "POST"])

    async def test_an_allowed_origin_reads_the_too_long_refusal_body(self):
        got = await self.fetch(self.allowed_page, "/api/jobs", template_job(MADALENA))
        self.assertEqual(got.get("status"), 422, got)
        body = json.loads(got["body"])
        self.assertEqual((body["code"], body["acceptable"]), ("too_long", True))
        self.assertEqual(self.queue.jobs(), [])

    async def test_an_allowed_origin_resends_the_too_long_job_with_accept_long_and_reads_the_201(self):
        got = await self.fetch(self.allowed_page, "/api/jobs", template_job(MADALENA, accept_long=True))
        self.assertEqual(got.get("status"), 201, got)

    async def test_an_allowed_origin_cannot_read_the_admin_job_list_even_as_an_admin(self):
        self.proxy_email = ADMIN_EMAIL
        got = await self.fetch(self.allowed_page, "/api/jobs")
        self.assertEqual(got, {"error": "TypeError"})
        self.assertEqual(self.forwarded, [("GET", "/api/jobs", 200)])

    async def test_a_disallowed_origin_can_read_and_send_nothing(self):
        calls = {
            "GET /api/me": ("/api/me", None),
            "POST /api/jobs": ("/api/jobs", template_job(TEST_PAGE)),
            "GET /api/jobs": ("/api/jobs", None),
        }
        for name, (path, job) in calls.items():
            with self.subTest(name):
                self.assertEqual(await self.fetch(self.other_page, path, job), {"error": "TypeError"})
        self.assertNotIn("POST", [method for method, _, _ in self.forwarded])
        self.assertEqual(self.queue.jobs(), [])


if __name__ == "__main__":
    unittest.main()
