"""HTTP routes of the print server: job intake, the admin API and the sender web form."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
import logging
import re
import time
import tomllib
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from aiohttp import web

from access_auth import HEADER, AccessDenied, AccessVerifier
from device_hub import DeviceHub, bearer_token
from job_artifacts import ESCPOS, PRINT_PNG, ArtifactStore, artifacts_root, job_files
from job_queue import (
    DEFAULT_EXPIRY_SECONDS, PRINTER_FIELDS, Job, JobNotFinal, JobQueue, PrinterState, SourceActivity, Status,
)
from render_job import KINDS, LONG_MAX_HEIGHT_DOTS, MAX_HEIGHT_DOTS, RenderError, render
from server_config import ServerConfig
from ticket_templates import DOTS_PER_CM, length_cm

MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_EXPIRES_IN = 7 * 86400
RATE_WINDOW_SECONDS = 600
# Each receipt or template render starts a Chromium.
RENDER_CONCURRENCY = 2
MAX_TITLE_LENGTH = 200
MAX_LIST_LIMIT = 1000


class _RenderSlots:
    """The render semaphore, counting the renders that hold or wait for a slot."""

    def __init__(self, size: int) -> None:
        self._semaphore = asyncio.Semaphore(size)
        self.in_progress = 0

    async def __aenter__(self) -> None:
        self.in_progress += 1
        try:
            await self._semaphore.acquire()
        except BaseException:
            self.in_progress -= 1
            raise

    async def __aexit__(self, *_) -> None:
        self._semaphore.release()
        self.in_progress -= 1


HUB = web.AppKey("hub", DeviceHub)

log = logging.getLogger("http_api")

_SEND_PAGE = (Path(__file__).resolve().parent / "static" / "send.html").read_text(encoding="utf-8")
[_SEND_SCRIPT] = re.findall(r"<script>(.*?)</script>", _SEND_PAGE, re.DOTALL)
_SEND_PAGE_CSP = (
    "default-src 'none'; "
    f"script-src 'sha256-{base64.b64encode(hashlib.sha256(_SEND_SCRIPT.encode()).digest()).decode()}'; "
    "style-src 'unsafe-inline'; img-src data: blob:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class ApiError(Exception):
    def __init__(self, status: int, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details or {}


class Role(StrEnum):
    ADMIN = "admin"
    CLIENT = "client"
    WEB = "web"


@dataclass(frozen=True)
class Caller:
    role: Role
    source: str
    ingress: str
    email: str | None = None


def _error(status: int, message: str, details: dict | None = None) -> web.Response:
    return web.json_response({"error": message, **(details or {})}, status=status)


@web.middleware
async def _errors(request: web.Request, handler) -> web.StreamResponse:
    try:
        return await handler(request)
    except ApiError as error:
        return _error(error.status, error.message, error.details)
    except web.HTTPRequestEntityTooLarge:
        return _error(413, f"the body is over {MAX_BODY_BYTES // (1024 * 1024)} MB")
    except web.HTTPException as error:
        if error.status < 400:
            raise
        return _error(error.status, error.reason)
    except Exception:
        log.exception("%s %s failed", request.method, request.path)
        return _error(500, "internal server error")


def _too_long(length_dots: int, accepted: bool) -> dict:
    """What a sender needs to decide whether to resend a too-long template job with ``accept_long``."""
    return {
        "code": "too_long",
        "length_cm": length_cm(length_dots),
        "limit_cm": (LONG_MAX_HEIGHT_DOTS if accepted else MAX_HEIGHT_DOTS) // DOTS_PER_CM,
        "acceptable": not accepted and length_dots <= LONG_MAX_HEIGHT_DOTS,
    }


def _job_json(job: Job, *, events: bool = False) -> dict:
    data = {f.name: getattr(job, f.name) for f in dataclasses.fields(job) if f.name not in ("data", "events")}
    if events:
        data["events"] = [dataclasses.asdict(event) for event in job.events]
    return data


class _Api:
    def __init__(self, config: ServerConfig, queue: JobQueue, hub: DeviceHub, verifier: AccessVerifier | None) -> None:
        self.config = config
        self.queue = queue
        self.hub = hub
        self.verifier = verifier
        self.artifacts = ArtifactStore(artifacts_root(config.database))
        self.render_slots = _RenderSlots(RENDER_CONCURRENCY)
        self.web_jobs: dict[str, deque[float]] = {}
        self.started = time.monotonic()
        self.started_at = time.time()

    async def caller(self, request: web.Request) -> Caller:
        token = bearer_token(request)
        if token is not None:
            if self.config.is_admin(token):
                return Caller(Role.ADMIN, "admin", "cli")
            client = self.config.client_for_token(token)
            if client is not None:
                return Caller(Role.CLIENT, client.id, "api")
            log.warning("refused %s %r: unknown bearer token", request.method, request.path)
            raise ApiError(401, "no valid credential")
        assertion = request.headers.get(HEADER)
        if assertion is not None and self.verifier is not None:
            try:
                email = await self.verifier.verify(assertion)
            except AccessDenied as denied:
                log.warning("refused %s %r: %s", request.method, request.path, denied.reason)
                raise ApiError(401, "no valid credential") from None
            if request.method == "POST":
                self.check_same_site(request)
            if self.config.is_admin_email(email):
                return Caller(Role.ADMIN, email, "admin-web", email)
            return Caller(Role.WEB, email, "web", email)
        raise ApiError(401, "no valid credential")

    @staticmethod
    def check_same_site(request: web.Request) -> None:
        """Refuse a cross-site POST that rides on the browser's Access cookie. Bearer callers need no check."""
        if request.content_type != "application/json":
            raise ApiError(403, "send the request with Content-Type: application/json")
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            raise ApiError(403, "cross-site requests are refused")

    async def admin(self, request: web.Request) -> Caller:
        caller = await self.caller(request)
        if caller.role is not Role.ADMIN:
            raise ApiError(403, "admin only")
        return caller

    async def web_sender(self, request: web.Request) -> Caller:
        caller = await self.caller(request)
        if caller.email is None:
            raise ApiError(403, "only for web senders")
        return caller

    async def body(self, request: web.Request, *, optional: bool = False) -> dict:
        return self.parse(await self.read(request), optional=optional)

    @staticmethod
    async def read(request: web.Request) -> bytes:
        if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY_BYTES, actual_size=request.content_length)
        return await request.read()

    @staticmethod
    def parse(raw: bytes, *, optional: bool = False) -> dict:
        if not raw and optional:
            return {}
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            raise ApiError(400, "the body is not valid JSON") from None
        if not isinstance(data, dict):
            raise ApiError(400, "the body must be a JSON object")
        return data

    def printer(self, printer_id: object):
        if not isinstance(printer_id, str):
            raise ApiError(400, "printer must be a printer id")
        printer = self.config.printers.get(printer_id)
        if printer is None:
            raise ApiError(404, "unknown printer")
        return printer

    def job(self, request: web.Request) -> Job:
        job = self.queue.job(request.match_info["id"])
        if job is None:
            raise ApiError(404, "unknown job")
        return job

    def check_rate(self, email: str) -> None:
        now = time.monotonic()
        for sender, times in list(self.web_jobs.items()):
            while times and times[0] <= now - RATE_WINDOW_SECONDS:
                times.popleft()
            if not times:
                del self.web_jobs[sender]
        sent = self.web_jobs.setdefault(email.lower(), deque())
        if len(sent) >= self.config.access.web_rate_limit:
            raise ApiError(429, "too many jobs; try again in a few minutes")
        sent.append(now)

    @staticmethod
    async def saving_artifacts(staging) -> Path:
        try:
            return await staging
        except Exception:
            log.exception("writing the artifacts of a job failed")
            raise ApiError(500, "saving the job failed on the server") from None

    async def post_job(self, request: web.Request) -> web.Response:
        caller = await self.caller(request)
        raw = await self.read(request)
        body = self.parse(raw)
        printer = self.printer(body.get("printer"))
        if caller.role is Role.WEB and not printer.public:
            raise ApiError(403, "this printer does not take jobs from the web form")
        kind = body.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ApiError(400, f"kind must be one of: {', '.join(KINDS)}")
        accept_long = body.get("accept_long", False)
        if not isinstance(accept_long, bool):
            raise ApiError(400, "accept_long must be true or false")
        if "accept_long" in body and kind != "template":
            raise ApiError(400, "accept_long is only for template jobs")
        title = body.get("title", "")
        if not isinstance(title, str) or len(title) > MAX_TITLE_LENGTH:
            raise ApiError(400, f"title must be text of at most {MAX_TITLE_LENGTH} characters")
        expires_in = body.get("expires_in", DEFAULT_EXPIRY_SECONDS)
        # bool is an int subclass, so `true` would pass as 1 second.
        number = isinstance(expires_in, (int, float)) and not isinstance(expires_in, bool)
        if not number or not 1 <= expires_in <= MAX_EXPIRES_IN:
            raise ApiError(400, f"expires_in must be a number of seconds from 1 to {MAX_EXPIRES_IN}")
        payload = image = None
        if kind in ("receipt", "template", "text"):
            payload = body.get("payload")
            if not isinstance(payload, dict):
                raise ApiError(400, f"a {kind} job needs a payload object")
        else:
            encoded = body.get("image")
            if not isinstance(encoded, str) or not encoded:
                raise ApiError(400, "an image job needs image, the file as base64")
            try:
                image = base64.b64decode(encoded, validate=True)
            except ValueError:
                raise ApiError(400, "image is not valid base64") from None
        if caller.role is Role.WEB:
            self.check_rate(caller.email)

        async with self.render_slots:
            try:
                rendered = await asyncio.to_thread(render, kind, payload=payload, image=image, accept_long=accept_long)
            except RenderError as error:
                if kind == "template" and error.length_dots is not None:
                    raise ApiError(422, str(error), _too_long(error.length_dots, accept_long)) from None
                raise ApiError(422, str(error)) from None
            except Exception:
                log.exception("rendering a %s job for %s failed", kind, caller.source)
                raise ApiError(500, "rendering failed on the server") from None

        now = time.time()
        template = payload["template"] if kind in ("template", "text") else None
        staged = await self.saving_artifacts(asyncio.to_thread(lambda: self.artifacts.stage(job_files(
            kind, rendered, request=None if kind == "image" else raw, image=image, template=template, created_at=now))))
        try:
            job = self.queue.add(
                printer.id, rendered.escpos, kind=kind, title=title, source=caller.source, ingress=caller.ingress,
                width=rendered.width, height=rendered.height, render_ms=rendered.render_ms,
                artifacts=staged, expires_in=expires_in, now=now,
            )
        finally:
            self.artifacts.discard(staged)
        log.info("job %s queued for %s by %s via %s (%d dots tall)", job.id, printer.id, caller.source,
                 caller.ingress, job.height)
        self.hub.notify(printer.id)
        return web.json_response(_job_json(job), status=201)

    async def list_jobs(self, request: web.Request) -> web.Response:
        await self.admin(request)
        query = request.query
        status = None
        if query.get("status"):
            try:
                status = Status(query["status"])
            except ValueError:
                raise ApiError(400, f"status must be one of: {', '.join(Status)}") from None
        try:
            limit = int(query.get("limit", 100))
        except ValueError:
            limit = 0
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise ApiError(400, f"limit must be a whole number from 1 to {MAX_LIST_LIMIT}")
        jobs = self.queue.jobs(query.get("printer") or None, status, limit=limit)
        return web.json_response({"jobs": [_job_json(job) for job in jobs]})

    async def get_job(self, request: web.Request) -> web.Response:
        await self.admin(request)
        job = self.job(request)
        folder = self.artifacts.folder(job.id)
        return web.json_response({**_job_json(job, events=True), "artifacts": str(folder) if folder.is_dir() else None})

    async def job_image(self, request: web.Request) -> web.Response:
        await self.admin(request)
        job = self.job(request)
        png = self.artifacts.read(job.id, PRINT_PNG)
        if png is None:
            raise ApiError(404, f"job {job.id} has no artifact folder with its image")
        return web.Response(body=png, content_type="image/png", headers={"X-Content-Type-Options": "nosniff"})

    async def cancel(self, request: web.Request) -> web.Response:
        caller = await self.admin(request)
        job = self.job(request)
        if not self.queue.cancel(job.id):
            raise ApiError(409, f"the job is already {self.job(request).status}")
        log.info("job %s cancelled by %s", job.id, caller.source)
        return web.json_response(_job_json(self.job(request)))

    async def reprint(self, request: web.Request) -> web.Response:
        caller = await self.admin(request)
        body = await self.body(request, optional=True)
        original = self.job(request)
        printer = self.printer(body.get("printer", original.printer))
        if original.status in (Status.QUEUED, Status.SENDING):
            raise ApiError(409, f"the job is still {original.status}")
        data = self.artifacts.read(original.id, ESCPOS)
        if data is None:
            raise ApiError(409, f"job {original.id} has no artifact folder with its printer bytes, "
                                f"so it cannot be reprinted")
        now = time.time()
        staged = await self.saving_artifacts(
            asyncio.to_thread(self.artifacts.stage_reprint, original.id, created_at=now))
        try:
            job = self.queue.reprint(original.id, printer.id, data, source=caller.source, ingress=caller.ingress,
                                     artifacts=staged, now=now)
        except JobNotFinal as error:
            raise ApiError(409, str(error)) from None
        finally:
            self.artifacts.discard(staged)
        if job is None:
            raise ApiError(404, "unknown job")
        log.info("job %s queued for %s by %s as a reprint of %s", job.id, printer.id, caller.source, original.id)
        self.hub.notify(printer.id)
        return web.json_response(_job_json(job), status=201)

    async def clear(self, request: web.Request) -> web.Response:
        caller = await self.admin(request)
        printer = self.printer(request.match_info["id"])
        cancelled = self.queue.clear(printer.id)
        log.info("printer %s cleared by %s: %d jobs cancelled", printer.id, caller.source, cancelled)
        return web.json_response({"cancelled": cancelled})

    async def move(self, request: web.Request) -> web.Response:
        caller = await self.admin(request)
        source = self.printer(request.match_info["id"])
        body = await self.body(request)
        target = self.printer(body.get("to"))
        if target.id == source.id:
            raise ApiError(400, "to must be another printer")
        moved = self.queue.move(source.id, target.id)
        log.info("%d jobs moved from %s to %s by %s", moved, source.id, target.id, caller.source)
        self.hub.notify(target.id)
        return web.json_response({"moved": moved})

    async def printers(self, request: web.Request) -> web.Response:
        await self.admin(request)
        result = []
        for printer in self.config.printers.values():
            state = self.queue.printer_state(printer.id) or PrinterState(printer.id)
            stats = self.queue.stats(printer=printer.id)
            result.append({
                "id": printer.id,
                "name": printer.name,
                "place": printer.place,
                "public": printer.public,
                "online": self.hub.online(printer.id),
                **{name: getattr(state, name) for name in PRINTER_FIELDS},
                "current_job": self.hub.current_job(printer.id),
                "paused_until": self.hub.paused_until(printer.id),
                "queued": stats.queued,
                "printed_today": stats.printed_today,
            })
        return web.json_response({"printers": result})

    async def stats(self, request: web.Request) -> web.Response:
        await self.admin(request)
        stats = self.queue.stats()
        hourly = {printer_id: stats.hourly.get(printer_id, [0] * 24) for printer_id in self.config.printers}
        return web.json_response({**dataclasses.asdict(stats), "hourly": hourly})

    async def me(self, request: web.Request) -> web.Response:
        caller = await self.web_sender(request)
        printers = [
            {"id": p.id, "name": p.name, "place": p.place} for p in self.config.printers.values() if p.public
        ]
        return web.json_response({"email": caller.email, "printers": printers})

    async def index(self, request: web.Request) -> web.Response:
        await self.web_sender(request)
        return web.Response(text=_SEND_PAGE, content_type="text/html",
                            headers={"Content-Security-Policy": _SEND_PAGE_CSP})

    async def admin_page(self, request: web.Request) -> web.Response:
        return web.Response(body=_ADMIN_PAGE, content_type="text/html", charset="utf-8", headers={
            "Content-Security-Policy": _ADMIN_PAGE_CSP, "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache",
        })

    async def admin_asset(self, request: web.Request) -> web.Response:
        asset = _ADMIN_ASSETS.get(request.match_info["name"])
        if asset is None:
            raise ApiError(404, "Not Found")
        body, content_type = asset
        charset = "utf-8" if content_type.startswith("text/") else None
        return web.Response(body=body, content_type=content_type, charset=charset, headers={
            "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache",
        })

    async def clients(self, request: web.Request) -> web.Response:
        """Each configured client, then each web sender seen, newest first."""
        await self.admin(request)
        activity = self.queue.activity(("api", "web"))
        by_client = {seen.source: seen for seen in activity if seen.ingress == "api"}
        clients = [_client_json(client_id, "client", by_client.get(client_id)) for client_id in self.config.clients]
        senders = [_client_json(seen.source, "web", seen) for seen in activity if seen.ingress == "web"]
        return web.json_response({"clients": clients + senders})

    async def server(self, request: web.Request) -> web.Response:
        await self.admin(request)
        return web.json_response({
            "version": SERVER_VERSION,
            "started_at": self.started_at,
            "uptime_seconds": round(time.monotonic() - self.started, 1),
            "renders_in_progress": self.render_slots.in_progress,
        })


_ROOT = Path(__file__).resolve().parent.parent
_ADMIN_DIR = Path(__file__).resolve().parent / "static" / "admin"
_ADMIN_ASSETS = {
    "admin.css": ((_ADMIN_DIR / "admin.css").read_bytes(), "text/css"),
    "admin.js": ((_ADMIN_DIR / "admin.js").read_bytes(), "text/javascript"),
    **{font.relative_to(_ADMIN_DIR).as_posix(): (font.read_bytes(), "font/woff2")
       for font in _ADMIN_DIR.glob("fonts/*/*.woff2")},
}
_ADMIN_PAGE = (_ADMIN_DIR / "index.html").read_bytes()
_ADMIN_PAGE_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; font-src 'self'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SERVER_VERSION = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _client_json(client_id: str, kind: str, seen: SourceActivity | None) -> dict:
    last = seen.last_job if seen else None
    return {
        "id": client_id, "kind": kind, "jobs_today": seen.jobs_today if seen else 0,
        "last_job": None if last is None else {
            "id": last.id, "title": last.title, "kind": last.kind, "printer": last.printer,
            "created_at": last.created_at,
        },
    }


def create_app(config: ServerConfig, queue: JobQueue, *, verifier: AccessVerifier | None = None) -> web.Application:
    """The whole server: HTTP routes plus ``GET /device``. Without ``[access]`` every web sender is refused."""
    if config.access is None:
        verifier = None
    elif verifier is None:
        verifier = AccessVerifier(config.access.team_domain, config.access.audience)
    hub = DeviceHub(config, queue)
    api = _Api(config, queue, hub, verifier)

    app = web.Application(client_max_size=MAX_BODY_BYTES + 1, middlewares=[_errors])
    app[HUB] = hub
    app.router.add_get("/device", hub.handle)
    app.router.add_post("/api/jobs", api.post_job)
    app.router.add_get("/api/jobs", api.list_jobs)
    app.router.add_get("/api/jobs/{id}", api.get_job)
    app.router.add_get("/api/jobs/{id}/image", api.job_image)
    app.router.add_post("/api/jobs/{id}/cancel", api.cancel)
    app.router.add_post("/api/jobs/{id}/reprint", api.reprint)
    app.router.add_post("/api/printers/{id}/clear", api.clear)
    app.router.add_post("/api/printers/{id}/move", api.move)
    app.router.add_get("/api/printers", api.printers)
    app.router.add_get("/api/stats", api.stats)
    app.router.add_get("/api/me", api.me)
    app.router.add_get("/", api.index)
    app.router.add_get("/admin", api.admin_page)
    app.router.add_get("/admin/{name:.+}", api.admin_asset)
    app.router.add_get("/api/clients", api.clients)
    app.router.add_get("/api/server", api.server)

    async def start(_: web.Application) -> None:
        swept = api.artifacts.sweep()
        if swept:
            log.info("deleted %d unfinished artifact folders in %s", swept, api.artifacts.root)
        hub.start()

    async def stop(_: web.Application) -> None:
        await hub.shutdown()

    app.on_startup.append(start)
    app.on_shutdown.append(stop)
    return app
