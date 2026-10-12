import asyncio
import dataclasses
import json
import re
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, expect

_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS.parent / "src"))
sys.path.insert(0, str(_TESTS))

from render_job import render  # noqa: E402
from test_device_hub import HubTestCase  # noqa: E402
from test_http_api import ADMIN_EMAIL, ADMIN_TOKEN, RENDERED, SAMPLE_PAYLOAD, SENDER_EMAIL  # noqa: E402

ADMIN_DIR = _TESTS.parent / "src" / "static" / "admin"
RECEIPT = render("receipt", payload=SAMPLE_PAYLOAD)
HOSTILE = '<img src=x onerror="document.title=\'pwned\'">'
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; font-src 'self'; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
FONT_URLS = re.findall(r'url\("(/admin/[^"]+)"\)', (ADMIN_DIR / "admin.css").read_text(encoding="utf-8"))


class AdminPageRouteTest(HubTestCase):
    async def test_admin_serves_the_page_with_a_strict_csp_and_no_data_to_anyone(self):
        self.add_job()
        response = await self.client.get("/admin")
        self.assertEqual((response.status, response.content_type), (200, "text/html"))
        self.assertEqual(response.headers["Content-Security-Policy"], CSP)
        self.assertEqual(await response.read(), (ADMIN_DIR / "index.html").read_bytes())
        self.assertNotIn(b"Holiday photo", await response.read())

    async def test_admin_assets_are_the_files_and_nothing_else_is_served(self):
        for name, content_type in (("admin.css", "text/css"), ("admin.js", "text/javascript")):
            with self.subTest(name=name):
                response = await self.client.get("/admin/" + name)
                self.assertEqual((response.status, response.content_type), (200, content_type))
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(await response.read(), (ADMIN_DIR / name).read_bytes())
        for name in ("index.html", "..%2Fhttp_api.py", "admin.js.map", ""):
            with self.subTest(name=name):
                status, _ = await self.call("GET", "/admin/" + name)
                self.assertEqual(status, 404)

    async def test_every_font_the_css_names_is_served_as_woff2_and_nothing_else_in_fonts_is(self):
        self.assertEqual(len(FONT_URLS), 2)
        for url in FONT_URLS:
            with self.subTest(url=url):
                response = await self.client.get(url)
                self.assertEqual((response.status, response.content_type, response.charset), (200, "font/woff2", None))
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(await response.read(), (ADMIN_DIR / url.removeprefix("/admin/")).read_bytes())
        for name in ("fonts/geist/OFL.txt", "fonts/geist/SOURCE.txt", "fonts/geist/", "fonts/Geist-Variable.woff2",
                     "fonts/geist/..%2F..%2F..%2Fhttp_api.py",
                     "admin.css/", "/admin.css"):
            with self.subTest(name=name):
                status, _ = await self.call("GET", "/admin/" + name)
                self.assertEqual(status, 404)

    def test_the_page_references_nothing_outside_its_own_origin_and_never_uses_inner_html(self):
        for name in ("index.html", "admin.css", "admin.js"):
            with self.subTest(name=name):
                text = (ADMIN_DIR / name).read_text(encoding="utf-8")
                text = re.sub(r'url\("/admin/fonts/[a-z]+/[A-Za-z-]+\.woff2"\)', "", text)
                self.assertNotRegex(text, r"(?i)https?:|//[a-z0-9.-]+\.[a-z]{2}|@import|\burl\(")
                self.assertNotRegex(text, r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(")
        html = (ADMIN_DIR / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r"\bstyle=|<script>|<style>|\bon[a-z]+=")
        for attribute in re.findall(r'(?:src|href)\s*=\s*"([^"]*)"', html):
            self.assertTrue(attribute.startswith(("/admin/", "#", "data:")), attribute)
        script = (ADMIN_DIR / "admin.js").read_text(encoding="utf-8")
        self.assertNotIn("localStorage", script)


class AdminBrowserCase(HubTestCase):
    """Chromium drives the admin page against the real app, a real device session and seeded jobs."""

    seeded = True

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.origin = str(self.client.make_url("")).rstrip("/")
        if self.seeded:
            self.seed()
            self.device = await self.connect()
            self.header, _, _ = await self.receive_job(self.device)
            await self.until(lambda: (self.hub.current_job("home") or {}).get("frames_sent") == self.printing.frames)
        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.requests: list = []
        self.console: list[str] = []
        self.crashes: list[str] = []

    async def asyncTearDown(self) -> None:
        for request in self.requests:
            self.assertTrue(request.url.startswith((self.origin + "/", "data:", "blob:")), request.url)
        self.assertEqual([line for line in self.console if "Content Security Policy" in line], [])
        self.assertEqual(self.crashes, [])
        await super().asyncTearDown()

    def add(self, printer: str, rendered, *, title: str, source: str, ingress: str, at: float):
        return self.queue.add(
            printer, rendered.escpos, kind="image" if rendered is RENDERED else "receipt", title=title, source=source,
            ingress=ingress, png=rendered.png, width=rendered.width, height=rendered.height,
            render_ms=rendered.render_ms, now=at,
        )

    def seed(self) -> None:
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today = max(midnight + 60, time.time() - 900)
        yesterday = midnight - 4 * 3600
        queue = self.queue
        self.old = self.add("home", RECEIPT, title="Evening brief", source="morning-brief", ingress="api", at=yesterday)
        queue.take("home", now=yesterday + 1)
        queue.confirm(self.old.id, now=yesterday + 9)
        self.printed = self.add("home", RENDERED, title="Holiday photo", source=SENDER_EMAIL, ingress="web", at=today)
        queue.take("home", now=today + 1)
        queue.confirm(self.printed.id, now=today + 8)
        self.retried = self.add("home", RECEIPT, title="Morning brief", source="morning-brief", ingress="api",
                                at=today + 20)
        queue.take("home", now=today + 21)
        queue.release(self.retried.id, detail="no reply in 120 s", now=today + 141)
        queue.take("home", now=today + 150)
        queue.confirm(self.retried.id, now=today + 158)
        self.hostile = self.add("home", RENDERED, title=HOSTILE, source=SENDER_EMAIL, ingress="web", at=today + 200)
        queue.take("home", now=today + 201)
        queue.confirm(self.hostile.id, now=today + 207)
        self.waiting = self.add("office", RECEIPT, title="Office checklist", source="morning-brief", ingress="api",
                                at=today + 300)
        self.waiting_too = self.add("office", RENDERED, title="Team photo", source="admin", ingress="cli",
                                    at=today + 310)
        self.printing = self.add("home", RECEIPT, title="Shopping list", source="morning-brief", ingress="api",
                                 at=time.time())

    async def new_page(self, *, width: int = 1440, height: int = 900, email: str | None = ADMIN_EMAIL):
        headers = self.web(email) if email else {}
        context = await self.browser.new_context(extra_http_headers=headers, viewport={"width": width, "height": height})
        self.addAsyncCleanup(context.close)
        page = await context.new_page()
        page.on("request", lambda request: self.requests.append(request))
        page.on("console", lambda message: self.console.append(message.text))
        page.on("pageerror", lambda error: self.crashes.append(str(error)))
        return page

    async def open(self, path: str = "/admin", *, width: int = 1440, height: int = 900, email: str | None = ADMIN_EMAIL,
                   ready: str | None = "#track .ticket"):
        page = await self.new_page(width=width, height=height, email=email)
        await page.goto(self.origin + path)
        if ready:
            await expect(page.locator(ready).first).to_be_visible()
        return page

    async def assertNoSideScroll(self, page) -> None:
        width = await page.evaluate("window.innerWidth")
        self.assertLessEqual(await page.evaluate("document.documentElement.scrollWidth"), width)

    @staticmethod
    def ticket(page, job):
        return page.locator("#track li.ticket").filter(has=page.locator(f'a[href="#/job/{job.id}"]'))


class AdminFontsTest(AdminBrowserCase):
    seeded = False

    async def test_geist_and_geist_mono_load_from_the_server_under_the_csp(self):
        page = await self.open(ready="#rail-empty")
        await page.evaluate("document.fonts.ready")
        loaded = await page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
        self.assertEqual(sorted(loaded), ["Geist", "Geist Mono"])
        self.assertTrue(await page.evaluate("document.fonts.check('16px Geist')"))
        self.assertTrue(await page.evaluate("document.fonts.check('16px \"Geist Mono\"')"))
        fonts = [request.url.removeprefix(self.origin) for request in self.requests if request.resource_type == "font"]
        self.assertEqual(sorted(fonts), sorted(FONT_URLS))


class AdminAuthTest(AdminBrowserCase):
    async def test_without_credentials_the_page_asks_for_the_token_and_shows_no_data(self):
        page = await self.open(email=None, width=360, height=740, ready="#token-form")
        await expect(page.locator("#gate-title")).to_have_text("Sign in")
        for hidden in ("#view-rail", "#view-job", "#view-connections", "#tabbar"):
            await expect(page.locator(hidden)).to_be_hidden()
        text = await page.locator("body").inner_text()
        for secret in ("Holiday photo", "Office", "morning-brief"):
            self.assertNotIn(secret, text)
        await self.assertNoSideScroll(page)

        await page.locator("#token").fill("not-the-admin-token-0000000000")
        await page.get_by_role("button", name="Sign in").click()
        await expect(page.locator("#gate-text")).to_contain_text("did not accept that token")
        await expect(page.locator("#track .ticket")).to_have_count(0)
        self.assertIsNone(await page.evaluate("sessionStorage.getItem('thermal-admin-token')"))

        async with page.expect_request(lambda r: r.url.endswith("/api/printers")) as sent:
            await page.locator("#token").fill(ADMIN_TOKEN)
            await page.get_by_role("button", name="Sign in").click()
        self.assertEqual((await sent.value).headers["authorization"], "Bearer " + ADMIN_TOKEN)
        await expect(self.ticket(page, self.printed)).to_be_visible()
        self.assertEqual(await page.evaluate("sessionStorage.getItem('thermal-admin-token')"), ADMIN_TOKEN)
        self.assertEqual(await page.evaluate("localStorage.length"), 0)

    async def test_a_web_sender_who_is_not_an_admin_sees_a_refusal_and_no_data(self):
        page = await self.open(email=SENDER_EMAIL, ready="#gate")
        await expect(page.locator("#gate-title")).to_have_text("Not an admin")
        await expect(page.locator("#token-form")).to_be_hidden()
        self.assertNotIn("Holiday photo", await page.locator("body").inner_text())


class AdminViewsTest(AdminBrowserCase):
    async def test_the_rail_shows_the_queue_now_and_history_from_the_real_api(self):
        page = await self.open()
        await expect(page.locator("#rail-title")).to_have_text("Home is printing Shopping list")
        await expect(page.locator("#rail-summary")).to_contain_text("2 waiting for an offline printer")
        keys = await page.locator("#track > li").evaluate_all(
            "items => items.map(i => i.classList.contains('marker') ? i.textContent.split(' ')[0]"
            " : i.querySelector('a').getAttribute('href').slice(6))")
        expected = [self.waiting_too.id, self.waiting.id, "now", self.printing.id, self.hostile.id, self.retried.id,
                    self.printed.id, "Today", self.old.id]
        self.assertEqual(keys[:len(expected)], expected)
        self.assertEqual(len(keys), len(expected) + 1)

        waiting = self.ticket(page, self.waiting)
        await expect(waiting.locator(".when")).to_contain_text("next")
        await expect(waiting.locator(".note")).to_have_text("waiting, printer offline")
        printing = self.ticket(page, self.printing)
        await expect(printing.locator(".progress small")).to_have_text(
            f"{self.printing.frames} of {self.printing.frames} chunks sent")
        retried = self.ticket(page, self.retried)
        await expect(retried.locator(".note")).to_have_text("printed on attempt 2")

        image = printing.locator("img")
        await expect(image).to_have_attribute("src", re.compile(r"^blob:"))
        size = await image.evaluate("img => [img.naturalWidth, img.naturalHeight]")
        self.assertEqual(size, [RECEIPT.width, RECEIPT.height])

        strip = page.locator("#fleet-strip")
        await expect(strip).to_contain_text(f"Printing {self.printing.frames}/{self.printing.frames}")
        await expect(strip).to_contain_text("Never connected")
        await expect(page.locator("#health")).to_have_text("1 printer offline")
        foot = await page.locator(".rail-foot").bounding_box()
        self.assertAlmostEqual(foot["y"] + foot["height"], 900, delta=1)

        await page.get_by_role("button", name="Office").click()
        await expect(page.locator("#track .ticket")).to_have_count(2)
        await expect(page.get_by_role("button", name="Office")).to_have_attribute("aria-pressed", "true")
        await page.get_by_role("button", name="Show stats").click()
        await expect(page.locator("#stats")).to_contain_text("Printed today")
        await expect(page.locator("#stats dd").first).to_have_text("3")

    async def test_the_detail_view_shows_the_image_events_and_raw_data_of_a_job(self):
        page = await self.open()
        await (self.ticket(page, self.retried)).click()
        await expect(page).to_have_url(re.compile(f"#/job/{self.retried.id}$"))
        await expect(page.locator("#job-title")).to_have_text("Morning brief")
        await expect(page.locator("#job-kicker")).to_have_text("Receipt from morning-brief")
        await expect(page.locator("#job-status")).to_contain_text("Printed on Home")
        events = await page.locator("#job-events strong").all_inner_texts()
        self.assertEqual(events, ["Received", "Rendered", "Sending", "Released", "Sending", "Printed"])
        await expect(page.locator("#job-events")).to_contain_text("no reply in 120 s")
        image = page.locator("#job-image")
        await expect(image).to_have_attribute("src", re.compile(r"^blob:"))
        self.assertEqual(await image.evaluate("img => [img.naturalWidth, img.naturalHeight]"),
                         [RECEIPT.width, RECEIPT.height])
        await page.get_by_text("Raw job data").click()
        await expect(page.locator("#job-raw")).to_contain_text(self.retried.id)
        await expect(page.locator("#job-raw")).to_contain_text(f"{RECEIPT.width} × {RECEIPT.height} dots")
        await expect(page.locator("#act-cancel")).to_be_hidden()

        await page.locator("#job-older").click()
        await expect(page.locator("#job-title")).to_have_text("Holiday photo")
        await page.goto(self.origin + "/admin#/job/00000000")
        await expect(page.locator("#job-title")).to_have_text("This job does not exist")

    async def test_connections_is_one_tab_and_the_old_printers_and_clients_links_open_it(self):
        page = await self.open()
        for nav in ("#tabs", "#tabbar"):
            await expect(page.locator(nav + " a")).to_have_text(["Rail", "Connections"])
        await expect(page.locator(".rail-foot .quiet-link")).to_have_attribute("href", "#/connections")
        for path in ("#/connections", "#/printers", "#/clients"):
            with self.subTest(path=path):
                await page.goto(self.origin + "/admin#/")
                await expect(page.locator("#view-rail")).to_be_visible()
                await page.goto(self.origin + "/admin" + path)
                await expect(page.locator(".printer-card")).to_have_count(2)
                await expect(page).to_have_title("Connections - Thermal")
                await expect(page.locator("#view-connections h2")).to_have_text(["Printers", "Clients"])
                await expect(page.locator('#tabs a[aria-current="page"]')).to_have_text("Connections")

    async def test_the_connections_view_shows_printers_server_and_clients(self):
        page = await self.open("/admin#/connections", ready=".printer-card")
        cards = page.locator(".printer-card")
        await expect(cards).to_have_count(2)
        home, office = cards.nth(0), cards.nth(1)
        await expect(home.locator(".name")).to_have_text("Home")
        await expect(home).to_contain_text("Home office")
        await expect(home.locator(".state")).to_contain_text("Printing")
        await expect(home.locator(".hours-scale")).to_contain_text("3 today")
        await expect(office.locator(".state")).to_have_text("Never connected")
        await expect(office.locator(".facts")).to_contain_text("2 jobs waiting")
        await expect(office.get_by_role("button", name="Move 2 jobs…")).to_be_visible()
        await expect(page.locator("#server-card")).to_contain_text("version 0.1.0")
        await expect(page.locator("#routes")).to_contain_text("Direct")

        await home.get_by_text("Details").click()
        await expect(home.locator("dl")).to_contain_text("python/1")
        await asyncio.sleep(3.5)
        await expect(home.locator("details")).to_have_attribute("open", "")

        clients = page.locator("#client-list li")
        await expect(clients).to_have_count(2)
        await expect(clients.nth(0)).to_contain_text("morning-brief")
        await expect(clients.nth(0)).to_contain_text("API client")
        await expect(clients.nth(0)).to_contain_text("Shopping list")
        await expect(clients.nth(1)).to_contain_text(SENDER_EMAIL)
        await expect(clients.nth(1)).to_contain_text("Web sender")
        await expect(clients.nth(1).locator(".count")).to_have_text("2 today")

    async def test_nothing_scrolls_sideways_at_360_px_in_any_view(self):
        page = await self.open(width=360, height=740)
        await self.assertNoSideScroll(page)
        heading = await self.ticket(page, self.old).evaluate("li => li.previousElementSibling.className")
        self.assertEqual(heading, "marker", "on a phone, a past day's label heads its jobs")
        await expect(page.locator("#tabbar")).to_be_visible()
        await expect(page.locator("#tabs")).to_be_hidden()
        await (self.ticket(page, self.printed)).click()
        await expect(page.locator("#job-title")).to_have_text("Holiday photo")
        await self.assertNoSideScroll(page)
        await page.get_by_role("button", name="Print on…").click()
        await expect(page.locator("#dialog")).to_be_visible()
        await self.assertNoSideScroll(page)
        await page.keyboard.press("Escape")
        await page.locator("#tabbar").get_by_role("link", name="Connections").click()
        await expect(page.locator(".printer-card")).to_have_count(2)
        await expect(page.locator("#client-list li")).to_have_count(2)
        await self.assertNoSideScroll(page)
        for target in await page.locator("#tabbar a, .printer-card button, .printer-card summary").all():
            box = await target.bounding_box()
            if box is None:
                continue
            self.assertGreaterEqual(box["height"], 44, await target.inner_text())

    @staticmethod
    async def scroll_state(sheet) -> dict:
        return await sheet.evaluate("s => ({top: s.scrollTop, height: s.scrollHeight, client: s.clientHeight})")

    @staticmethod
    async def at_bottom(page, sheet) -> None:
        await page.wait_for_function("s => s.scrollTop > 0 && s.scrollTop + s.clientHeight >= s.scrollHeight - 1",
                                     arg=await sheet.element_handle())

    async def test_a_tall_ticket_scrolls_on_its_own_and_keeps_its_place_across_a_poll(self):
        page = await self.open()
        tall = self.ticket(page, self.retried).locator(".paper-wrap")
        other = self.ticket(page, self.printing).locator(".paper-wrap")
        short = self.ticket(page, self.printed).locator(".paper-wrap")
        box = await tall.bounding_box()
        self.assertLessEqual(box["y"] + box["height"], 900, "the sheet ends inside the window")
        state = await self.scroll_state(tall)
        self.assertGreater(state["height"], state["client"], "the receipt is taller than its sheet")
        state = await self.scroll_state(short)
        self.assertEqual(state["height"], state["client"], "a short ticket does not scroll")
        image = await tall.locator("img").evaluate(
            "i => [i.clientWidth, i.clientHeight, i.closest('.paper').clientWidth, i.closest('.paper').clientHeight]")
        self.assertAlmostEqual(image[1] / image[0], RECEIPT.height / RECEIPT.width, delta=0.02, msg="not squeezed")
        self.assertGreater(image[2], 180, "the receipt keeps the sheet's width")
        rail_left = await page.locator("#rail").evaluate("r => r.scrollLeft")

        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await page.mouse.wheel(0, 20000)
        await self.at_bottom(page, tall)
        bottom = (await self.scroll_state(tall))["top"]
        self.assertEqual((await self.scroll_state(other))["top"], 0)
        self.assertEqual(await page.evaluate("window.scrollY"), 0)
        self.assertEqual(await page.locator("#rail").evaluate("r => r.scrollLeft"), rail_left)

        await tall.evaluate("s => { s.probe = true; }")
        late = self.add("office", RENDERED, title="Late arrival", source="admin", ingress="cli", at=time.time())
        await expect(self.ticket(page, late)).to_be_visible()
        self.assertEqual(await tall.evaluate("s => [s.probe === true, s.scrollTop]"), [True, bottom])

    async def test_a_ticket_keeps_its_scroll_when_a_poll_moves_it_along_the_rail(self):
        page = await self.open()
        sheet = self.ticket(page, self.printing).locator(".paper-wrap")
        await sheet.evaluate("s => { s.scrollTop = 120; s.probe = true; }")
        self.queue.take("office")
        await expect(self.ticket(page, self.waiting)).to_have_class(re.compile(r"\bsending\b"))
        self.assertEqual(await sheet.evaluate("s => [s.probe === true, s.scrollTop]"), [True, 120])

    async def test_a_sideways_wheel_over_a_ticket_still_moves_the_rail(self):
        page = await self.open()
        rail = await page.locator("#rail").element_handle()
        box = await self.ticket(page, self.retried).locator(".paper-wrap").bounding_box()
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        for shift, dx, dy in ((False, -300, 0), (True, 0, 150)):
            with self.subTest(shift=shift):
                start = await rail.evaluate("r => r.scrollLeft")
                if shift:
                    await page.keyboard.down("Shift")
                await page.mouse.wheel(dx, dy)
                await page.keyboard.up("Shift")
                await page.wait_for_function("([r, start]) => r.scrollLeft !== start", arg=[rail, start])

    async def test_on_a_phone_a_swipe_on_a_ticket_scrolls_only_that_ticket(self):
        page = await self.open(width=390, height=844)
        sheet = self.ticket(page, self.waiting).locator(".paper-wrap")
        other = self.ticket(page, self.printing).locator(".paper-wrap")
        box = await sheet.bounding_box()
        cdp = await page.context.new_cdp_session(page)
        for _ in range(2):
            await cdp.send("Input.synthesizeScrollGesture", {
                "x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2, "yDistance": -2000,
                "gestureSourceType": "touch", "speed": 3000,
            })
        await self.at_bottom(page, sheet)
        self.assertEqual((await self.scroll_state(other))["top"], 0)
        self.assertEqual(await page.evaluate("window.scrollY"), 0, "the page stays put at the sheet's end")

    async def test_hostile_titles_and_printer_names_render_as_text(self):
        office = self.config.printers["office"]
        self.config.printers["office"] = dataclasses.replace(office, name=HOSTILE)
        page = await self.open()
        await expect(page.locator("#fleet-strip")).to_contain_text(HOSTILE)
        hostile = self.ticket(page, self.hostile)
        await expect(hostile.locator(".title")).to_have_text(HOSTILE)
        await (self.ticket(page, self.hostile)).click()
        await expect(page.locator("#job-title")).to_have_text(HOSTILE)
        await page.goto(self.origin + "/admin#/connections")
        await expect(page.locator(".printer-card .name").nth(1)).to_have_text(HOSTILE)
        self.assertEqual(await page.locator('img[src="x"]').count(), 0)
        self.assertNotEqual(await page.title(), "pwned")

    async def test_keyboard_focus_scrolls_an_off_screen_ticket_into_the_rail(self):
        page = await self.open()
        link = page.locator(f'#track a[href="#/job/{self.old.id}"]')
        rail = await page.locator("#rail").bounding_box()
        self.assertLess((await link.bounding_box())["x"], rail["x"], "the oldest ticket starts off screen")
        await link.focus()
        await expect(link).to_be_focused()
        box = await link.bounding_box()
        self.assertGreaterEqual(box["x"], rail["x"])
        self.assertLessEqual(box["x"] + box["width"], rail["x"] + rail["width"])

    async def test_a_long_printer_name_is_cut_inside_its_ticket(self):
        home = self.config.printers["home"]
        self.config.printers["home"] = dataclasses.replace(home, name="The big printer in the kitchen by the window")
        page = await self.open()
        ticket = self.ticket(page, self.printed)
        name = ticket.locator(".when .printer")
        self.assertGreater(*await name.evaluate("e => [e.scrollWidth, e.clientWidth]"))
        name_box, ticket_box = await name.bounding_box(), await ticket.bounding_box()
        self.assertLessEqual(name_box["x"] + name_box["width"], ticket_box["x"] + ticket_box["width"])

    async def test_a_malformed_job_link_falls_back_to_the_rail(self):
        page = await self.open("/admin#/job/%")
        await expect(page.locator("#view-rail")).to_be_visible()
        await expect(page.locator("#view-job")).to_be_hidden()

    async def test_the_printer_filter_wraps_on_a_phone_instead_of_hiding_printers(self):
        office = self.config.printers["office"]
        for printer_id in ("garage", "studio", "parents", "grandma"):
            self.config.printers[printer_id] = dataclasses.replace(office, id=printer_id, name=printer_id.title(),
                                                                   token=printer_id + "-token-0123456789abcdef")
        page = await self.open(width=360, height=740)
        buttons = page.locator("#filters button")
        await expect(buttons).to_have_count(7)
        for button in await buttons.all():
            box = await button.bounding_box()
            self.assertLessEqual(box["x"] + box["width"], 360, await button.inner_text())
            self.assertGreaterEqual(box["height"], 44)
        await self.assertNoSideScroll(page)

    async def test_the_page_says_loading_until_the_first_data_arrives(self):
        page = await self.new_page()
        release = asyncio.Event()

        async def hold(route) -> None:
            await release.wait()
            await route.continue_()

        await page.route("**/api/printers", hold)
        await page.goto(self.origin + "/admin")
        await expect(page.locator("#loading")).to_have_text("Loading…")
        await expect(page.locator("#view-rail")).to_be_hidden()
        release.set()
        await expect(self.ticket(page, self.printed)).to_be_visible()
        await expect(page.locator("#loading")).to_be_hidden()

    async def test_polling_stops_while_the_tab_is_hidden_and_resumes_when_shown(self):
        page = await self.open()
        await page.evaluate("""() => {
            Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
            document.dispatchEvent(new Event("visibilitychange"));
        }""")
        await asyncio.sleep(0.5)
        before = len([r for r in self.requests if "/api/" in r.url])
        await asyncio.sleep(4)
        self.assertEqual(len([r for r in self.requests if "/api/" in r.url]), before)
        async with page.expect_request(lambda r: r.url.endswith("/api/printers")):
            await page.evaluate("""() => {
                Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
                document.dispatchEvent(new Event("visibilitychange"));
            }""")


class AdminEmptyTest(AdminBrowserCase):
    seeded = False

    async def test_with_no_jobs_the_empty_message_replaces_the_rail(self):
        page = await self.open(ready="#rail-empty")
        await expect(page.locator("#rail-empty")).to_contain_text("No jobs yet")
        await expect(page.locator("#rail")).to_be_hidden()
        foot = await page.locator(".rail-foot").bounding_box()
        self.assertAlmostEqual(foot["y"] + foot["height"], 900, delta=1)

    async def test_with_no_printers_the_header_says_so(self):
        self.config.printers.clear()
        page = await self.open(ready="#rail-empty")
        await expect(page.locator("#health")).to_have_text("No printers configured")


class AdminActionsTest(AdminBrowserCase):
    async def test_cancel_asks_first_then_cancels_through_the_api(self):
        page = await self.open(f"/admin#/job/{self.waiting.id}", ready="#act-cancel")
        await page.locator("#act-cancel").click()
        await expect(page.locator("#dialog-title")).to_have_text("Cancel this job?")
        await page.get_by_role("button", name="Go back").click()
        await expect(page.locator("#dialog")).to_be_hidden()
        self.assertEqual(self.queue.job(self.waiting.id).status, "queued")

        await page.locator("#act-cancel").click()
        await page.locator("#dialog").get_by_role("button", name="Cancel job").click()
        await expect(page.locator("#notice")).to_have_text("Job cancelled")
        self.assertEqual(self.queue.job(self.waiting.id).status, "cancelled")
        await expect(page.locator("#job-status")).to_contain_text("Cancelled on Office")
        await expect(page.locator("#act-cancel")).to_be_hidden()

    async def test_print_on_reprints_on_the_chosen_printer_as_the_admin(self):
        page = await self.open(f"/admin#/job/{self.printed.id}", ready="#act-print-on")
        await expect(page.locator("#job-title")).to_have_text("Holiday photo")
        await page.locator("#act-print-on").click()
        await page.locator("#dialog").get_by_text("Office", exact=True).click()
        await page.locator("#dialog").get_by_role("button", name="Print").click()
        await expect(page.locator("#notice")).to_have_text("Reprint queued on Office")
        copy = self.queue.jobs("office", "queued")[0]
        self.assertEqual((copy.title, copy.source, copy.ingress), ("Holiday photo", ADMIN_EMAIL, "admin-web"))
        self.assertEqual(self.queue.png(copy.id), RENDERED.png)

        await page.locator("#act-reprint").click()
        await expect(page.locator("#notice")).to_have_text("Reprint queued on Home")
        self.assertEqual(len(self.queue.jobs("home", "queued")), 1)

    async def test_a_refused_action_shows_the_servers_reason(self):
        page = await self.open(f"/admin#/job/{self.printed.id}", ready="#act-reprint")
        await page.route("**/reprint", lambda route: route.fulfill(
            status=409, content_type="application/json", body=json.dumps({"error": "the job is still queued"})))
        await page.locator("#act-reprint").click()
        await expect(page.locator("#notice")).to_have_text("The job is still queued.")
        await expect(page.locator("#notice")).to_have_class(re.compile("bad"))

    async def test_move_and_clear_act_on_the_printers_queue(self):
        page = await self.open("/admin#/connections", ready=".printer-card")
        office = page.locator(".printer-card").nth(1)
        await office.get_by_role("button", name="Move 2 jobs…").click()
        await page.locator("#dialog").get_by_role("button", name="Move jobs").click()
        await expect(page.locator("#notice")).to_have_text("2 jobs moved to Home")
        self.assertEqual({self.queue.job(j.id).printer for j in (self.waiting, self.waiting_too)}, {"home"})

        home = page.locator(".printer-card").nth(0)
        await expect(home.get_by_role("button", name="Clear queue")).to_be_visible()
        await home.get_by_role("button", name="Clear queue").click()
        await expect(page.locator("#dialog-text")).to_have_text(
            "2 queued jobs and the job printing now will be cancelled and will not print.")
        await page.locator("#dialog").get_by_role("button", name="Clear queue").click()
        await expect(page.locator("#notice")).to_have_text("3 jobs cancelled")
        statuses = {self.queue.job(j.id).status for j in (self.waiting, self.waiting_too, self.printing)}
        self.assertEqual(statuses, {"cancelled"})


if __name__ == "__main__":
    unittest.main()
