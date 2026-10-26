import asyncio
import base64
import hashlib
import io
import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.async_api import async_playwright, expect

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

from access_auth import HEADER  # noqa: E402
from render_job import render  # noqa: E402
from test_access_auth import STRANGER, claims, sign  # noqa: E402
from test_http_api import ADMIN_TOKEN, CLIENT_TOKEN, SENDER_EMAIL, ServerTestCase, photo_png  # noqa: E402

PAGE = (_TESTS.parent / "src" / "static" / "send.html").read_bytes()
RENDER_TIMEOUT_MS = 60_000
SIGNED_OUT = "Your sign-in expired \u2014 reload the page to sign in again."
LOGIN = "https://daily-printer.cloudflareaccess.com/cdn-cgi/access/login/print.example.com"
LONG_EMAIL = "maria.fernanda.albuquerque.oliveira@escritorioexemplo.com.br"
DIST = _TESTS.parent / "web" / "dist"
RECEIPT_ORIGIN = "http://receipt.invalid"
HEADER_FIT_JS = """(el) => {
  const text = document.createRange();
  text.selectNodeContents(el);
  return { scroll: el.scrollWidth, client: el.clientWidth, right: text.getBoundingClientRect().right,
           lines: text.getClientRects().length };
}"""


class SendPageRouteTest(ServerTestCase):
    async def test_get_root_serves_the_send_page_to_a_web_sender(self):
        response = await self.client.get("/", headers=self.web())
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/html")
        self.assertEqual(await response.read(), PAGE)

    async def test_get_root_sends_a_csp_that_allows_only_the_pages_own_script(self):
        [script] = re.findall(rb"<script>(.*?)</script>", PAGE, re.DOTALL)
        digest = base64.b64encode(hashlib.sha256(script).digest()).decode()
        response = await self.client.get("/", headers=self.web())
        self.assertEqual(response.headers["Content-Security-Policy"], (
            f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; img-src data: blob:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        ))

    async def test_get_root_refuses_everyone_who_is_not_a_web_sender(self):
        forged = sign(claims(), key=STRANGER, kid="a")
        self.secrets.append(forged)
        cases = {
            "no credential": ({}, 401),
            "forged Access token": ({HEADER: forged}, 401),
            "admin token": (self.bearer(ADMIN_TOKEN), 403),
            "client token": (self.bearer(CLIENT_TOKEN), 403),
        }
        for name, (headers, expected) in cases.items():
            with self.subTest(name):
                status, body = await self.call("GET", "/", headers)
                self.assertEqual(status, expected)
                self.assertNotIn(b"send-form", json.dumps(body).encode())

    def test_the_page_references_nothing_outside_its_own_origin(self):
        html = PAGE.decode()
        self.assertNotRegex(html, r"(?i)https?:|//[a-z0-9.-]+\.[a-z]|@import")
        for attribute in re.findall(r'(?:src|href|action)\s*=\s*"([^"]*)"', html):
            self.assertTrue(attribute.startswith("data:"), attribute)
        for url in re.findall(r"fetch\(\s*\"([^\"]*)\"", html):
            self.assertTrue(url.startswith("/api/"), url)


def refusal(status: int, error: str):
    async def handler(route) -> None:
        await route.fulfill(status=status, json={"error": error})
    return handler


class SendPageBrowserTest(ServerTestCase):
    """Chromium drives the page against the real app; the Access header stands in for Cloudflare's edge."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.origin = str(self.client.make_url("")).rstrip("/")
        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.requests: list[str] = []
        self.console: list[str] = []
        self.page = await self.new_page(SENDER_EMAIL)

    async def new_page(self, email: str):
        context = await self.browser.new_context(extra_http_headers=self.web(email),
                                                 viewport={"width": 360, "height": 740})
        page = await context.new_page()
        page.on("request", lambda request: self.requests.append(request.url))
        page.on("console", lambda message: self.console.append(message.text))
        return page

    async def asyncTearDown(self) -> None:
        for url in self.requests:
            self.assertTrue(url.startswith((self.origin + "/", "data:", "blob:")), url)
        self.assertEqual([line for line in self.console if "Content Security Policy" in line], [])
        await super().asyncTearDown()

    async def open(self, email: str = SENDER_EMAIL) -> None:
        await self.page.goto(self.origin + "/")
        await expect(self.page.locator("#who")).to_have_text(f"Signed in as {email}")
        await expect(self.page.locator("#send")).to_be_enabled()
        self.assertLessEqual(await self.page.evaluate("document.documentElement.scrollWidth"), 360)

    async def send(self):
        async with self.page.expect_request(lambda r: r.url.endswith("/api/jobs") and r.method == "POST") as sent:
            await self.page.locator("#send").click()
        return await sent.value

    async def test_a_message_goes_out_as_a_same_origin_json_receipt_job_and_is_queued(self):
        await self.open()
        await expect(self.page.locator("#printer-picker")).to_be_hidden()
        await expect(self.page.locator("#slot-name")).to_have_text("Home")
        await self.page.locator("#title").fill("Hello from Lisbon")
        await self.page.locator("#message").fill("Saw this and thought of you.\n\nSee you Friday!")

        request = await self.send()

        self.assertEqual((await request.all_headers())["content-type"], "application/json")
        body = request.post_data_json
        self.assertEqual(set(body), {"printer", "kind", "title", "payload"})
        self.assertEqual((body["printer"], body["kind"], body["title"]), ("home", "receipt", "Hello from Lisbon"))
        self.assertEqual(body["payload"]["schemaVersion"], 2)
        self.assertEqual(body["payload"]["blocks"], [
            {"type": "section_header", "title": SENDER_EMAIL},
            {"type": "day_header", "title": "Hello from Lisbon"},
            {"type": "task", "content": "Saw this and thought of you."},
            {"type": "task", "content": "See you Friday!"},
        ])
        await expect(self.page.locator("#result")).to_have_text("Queued for Home", timeout=RENDER_TIMEOUT_MS)
        self.assertEqual((await request.response()).status, 201)
        [job] = self.queue.jobs()
        self.assertEqual((job.printer, job.kind, job.title, job.source, job.ingress),
                         ("home", "receipt", "Hello from Lisbon", SENDER_EMAIL, "web"))
        self.assertEqual(job.width, 384)
        await expect(self.page.locator("#message")).to_have_value("")

    async def test_a_photo_is_downscaled_to_print_width_before_upload_and_is_queued(self):
        await self.open()
        await self.page.get_by_text("Photo", exact=True).click()
        await expect(self.page.locator("#message-panel")).to_be_hidden()
        await expect(self.page.locator("#title")).to_be_hidden()
        await self.page.locator("#photo").set_input_files(
            files=[{"name": "holiday.png", "mimeType": "image/png", "buffer": photo_png((1200, 900))}])
        await expect(self.page.locator("#preview")).to_be_visible()

        request = await self.send()

        body = request.post_data_json
        self.assertEqual(set(body), {"printer", "kind", "image"})
        self.assertEqual((body["printer"], body["kind"]), ("home", "image"))
        upload = Image.open(io.BytesIO(base64.b64decode(body["image"], validate=True)))
        self.assertEqual((upload.format, upload.size), ("JPEG", (384, 288)))
        await expect(self.page.locator("#result")).to_have_text("Queued for Home", timeout=RENDER_TIMEOUT_MS)
        [job] = self.queue.jobs()
        self.assertEqual((job.kind, job.source, job.width, job.height), ("image", SENDER_EMAIL, 384, 288))
        await expect(self.page.locator("#preview")).to_be_hidden()

    async def test_a_cancelled_pick_during_a_decode_re_enables_send(self):
        await self.open()
        await self.page.get_by_text("Photo", exact=True).click()
        await self.page.evaluate("window.Image = function () { return {}; }")
        await self.page.locator("#photo").set_input_files(
            files=[{"name": "holiday.png", "mimeType": "image/png", "buffer": photo_png((1200, 900))}])
        await expect(self.page.locator("#send")).to_be_disabled()
        await self.page.evaluate("""() => {
            const photo = document.getElementById("photo");
            photo.value = "";
            photo.dispatchEvent(new Event("change"));
        }""")
        await expect(self.page.locator("#send")).to_be_enabled()
        await expect(self.page.locator("#preview")).to_be_hidden()

    async def test_server_refusals_show_a_clear_line_and_keep_the_message(self):
        refusals = [
            (429, "too many jobs; try again in a few minutes", "That's a lot of prints!"),
            (422, "the receipt would print 65.0 cm long; the limit is 50 cm", "the receipt would print 65.0 cm long"),
            (413, "the body is over 10 MB", "That is too big to send."),
            (401, "no valid credential", SIGNED_OUT),
        ]
        await self.open()
        await self.page.locator("#message").fill("Ping!")
        for status, error, shown in refusals:
            with self.subTest(status=status):
                await self.page.unroute("**/api/jobs")
                await self.page.route("**/api/jobs", refusal(status, error))
                await self.send()
                await expect(self.page.locator("#result")).to_contain_text(shown)
                await expect(self.page.locator("#result")).to_have_attribute("data-tone", "error")
                await expect(self.page.locator("#message")).to_have_value("Ping!")
        self.assertEqual(self.queue.jobs(), [])

    async def test_an_expired_access_session_says_to_reload_instead_of_following_the_login_redirect(self):
        async def to_login(route) -> None:
            await route.fulfill(status=302, headers={"Location": LOGIN})

        await self.open()
        await self.page.route("**/api/jobs", to_login)
        await self.page.locator("#message").fill("Ping!")
        await self.send()
        await expect(self.page.locator("#result")).to_have_text(SIGNED_OUT)

        await self.page.route("**/api/me", to_login)
        await self.page.reload()
        await expect(self.page.locator("#who")).to_have_text(SIGNED_OUT)
        await expect(self.page.locator("#send")).to_be_disabled()
        self.assertEqual(self.queue.jobs(), [])

    async def test_a_long_email_wraps_on_the_receipt_instead_of_running_off_the_paper(self):
        self.assertEqual(len(LONG_EMAIL), 60)
        self.page = await self.new_page(LONG_EMAIL)
        await self.open(LONG_EMAIL)
        await self.page.locator("#message").fill("Hi!")

        request = await self.send()

        await expect(self.page.locator("#result")).to_have_text("Queued for Home", timeout=RENDER_TIMEOUT_MS)
        [job] = self.queue.jobs()
        payload = request.post_data_json["payload"]
        self.assertEqual(payload["blocks"][0], {"type": "section_header", "title": LONG_EMAIL})
        fit = await self.receipt_header_fit(payload)
        self.assertLessEqual(fit["scroll"], fit["client"])
        self.assertLessEqual(fit["right"], 384)
        self.assertGreaterEqual(fit["lines"], 2)
        payload["blocks"][0]["title"] = "ana@example.com"
        one_line = await asyncio.to_thread(render, "receipt", payload=payload)
        self.assertEqual((job.width, one_line.width), (384, 384))
        # A clipped email keeps one line; a wrapped one adds a line of text.
        self.assertGreater(job.height, one_line.height)

    async def receipt_header_fit(self, payload: dict) -> dict:
        """Text box of the sender header in the built receipt app at print width."""
        page = await self.browser.new_page(viewport={"width": 384, "height": 720})
        self.addAsyncCleanup(page.close)

        async def serve(route) -> None:
            path = urlsplit(route.request.url).path
            if path == "/payload.json":
                await route.fulfill(json=payload)
            else:
                await route.fulfill(path=DIST / path.lstrip("/"))

        await page.route(f"{RECEIPT_ORIGIN}/**", serve)
        await page.goto(f"{RECEIPT_ORIGIN}/index.html")
        return await page.locator("#receipt .section-header").evaluate(HEADER_FIT_JS)

    async def test_several_public_printers_offer_a_picker_and_names_stay_text(self):
        hostile = '<img src=x onerror="document.title=1">'
        me = {"email": SENDER_EMAIL, "printers": [
            {"id": "home", "name": "Home", "place": "Home office", "online": True, "last_seen": 1_700_000_000.0},
            {"id": "garden", "name": hostile, "place": "Shed", "online": False, "last_seen": None},
        ]}
        await self.page.route("**/api/me", lambda route: route.fulfill(json=me))
        await self.page.route("**/api/jobs", lambda route: route.fulfill(status=201, json={"id": "abc"}))
        await self.open()
        picker = self.page.locator("#printer-picker")
        await expect(picker).to_be_visible()
        await expect(picker.locator("img")).to_have_count(0)
        await picker.get_by_text("Shed").click()
        await expect(self.page.locator("#slot-name")).to_have_text(hostile)
        await self.page.locator("#message").fill("For the garden printer")

        request = await self.send()

        self.assertEqual(request.post_data_json["printer"], "garden")
        await expect(self.page.locator("#result")).to_have_text("Queued for " + hostile)
        self.assertEqual(await self.page.title(), "Send a print")


if __name__ == "__main__":
    unittest.main()
