"""HTTP routes of the print server: job intake, the admin API and the sender web form."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from aiohttp import web

from access_auth import HEADER, AccessDenied, AccessVerifier
from device_hub import DeviceHub, bearer_token
from job_queue import DEFAULT_EXPIRY_SECONDS, PRINTER_FIELDS, Job, JobNotFinal, JobQueue, PrinterState, Status
from render_job import KINDS, RenderError, escpos_from_png, render
from server_config import ServerConfig

MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_EXPIRES_IN = 7 * 86400
RATE_WINDOW_SECONDS = 600
# Each receipt render starts a Chromium.
RENDER_CONCURRENCY = 2
MAX_TITLE_LENGTH = 200
MAX_LIST_LIMIT = 1000

HUB = web.AppKey("hub", DeviceHub)

log = logging.getLogger("http_api")

_INDEX = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Print</title></head>
<body><p>The print form is not built yet.</p></body>
</html>
"""


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


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


def _error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


@web.middleware
async def _errors(request: web.Request, handler) -> web.StreamResponse:
    try:
        return await handler(request)
    except ApiError as error:
        return _error(error.status, error.message)
    except web.HTTPRequestEntityTooLarge:
        return _error(413, f"the body is over {MAX_BODY_BYTES // (1024 * 1024)} MB")
    except web.HTTPException as error:
        if error.status < 400:
            raise
        return _error(error.status, error.reason)
    except Exception:
        log.exception("%s %s failed", request.method, request.path)
        return _error(500, "internal server error")


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
        self.render_slots = asyncio.Semaphore(RENDER_CONCURRENCY)
        self.web_jobs: dict[str, deque[float]] = {}

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
        if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY_BYTES, actual_size=request.content_length)
        raw = await request.read()
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

    async def post_job(self, request: web.Request) -> web.Response:
        caller = await self.caller(request)
        body = await self.body(request)
        printer = self.printer(body.get("printer"))
        if caller.role is Role.WEB and not printer.public:
            raise ApiError(403, "this printer does not take jobs from the web form")
        kind = body.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ApiError(400, f"kind must be one of: {', '.join(KINDS)}")
        title = body.get("title", "")
        if not isinstance(title, str) or len(title) > MAX_TITLE_LENGTH:
            raise ApiError(400, f"title must be text of at most {MAX_TITLE_LENGTH} characters")
        expires_in = body.get("expires_in", DEFAULT_EXPIRY_SECONDS)
        # bool is an int subclass, so `true` would pass as 1 second.
        number = isinstance(expires_in, (int, float)) and not isinstance(expires_in, bool)
        if not number or not 1 <= expires_in <= MAX_EXPIRES_IN:
            raise ApiError(400, f"expires_in must be a number of seconds from 1 to {MAX_EXPIRES_IN}")
        payload = image = None
        if kind == "receipt":
            payload = body.get("payload")
            if not isinstance(payload, dict):
                raise ApiError(400, "a receipt job needs a payload object")
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
                rendered = await asyncio.to_thread(render, kind, payload=payload, image=image)
            except RenderError as error:
                raise ApiError(422, str(error)) from None
            except Exception:
                log.exception("rendering a %s job for %s failed", kind, caller.source)
                raise ApiError(500, "rendering failed on the server") from None

        job = self.queue.add(
            printer.id, rendered.escpos, kind=kind, title=title, source=caller.source, ingress=caller.ingress,
            png=rendered.png, width=rendered.width, height=rendered.height, render_ms=rendered.render_ms,
            expires_in=expires_in,
        )
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
        return web.json_response(_job_json(self.job(request), events=True))

    async def job_image(self, request: web.Request) -> web.Response:
        await self.admin(request)
        png = self.queue.png(request.match_info["id"])
        if png is None:
            raise ApiError(404, "unknown job, or its image was deleted after 30 days")
        return web.Response(body=png, content_type="image/png")

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
        png = self.queue.png(original.id)
        if png is None:
            raise ApiError(404, "the job's image was deleted after 30 days")
        async with self.render_slots:
            data = await asyncio.to_thread(escpos_from_png, png)
        try:
            job = self.queue.reprint(original.id, printer.id, data, source=caller.source, ingress=caller.ingress)
        except JobNotFinal as error:
            raise ApiError(409, str(error)) from None
        if job is None:
            raise ApiError(404, "the job's image was deleted after 30 days")
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
        hourly = {printer_id: [0] * 24 for printer_id in self.config.printers}
        hourly.update(stats.hourly)
        return web.json_response({**dataclasses.asdict(stats), "hourly": hourly})

    async def me(self, request: web.Request) -> web.Response:
        caller = await self.web_sender(request)
        printers = [
            {"id": p.id, "name": p.name, "place": p.place} for p in self.config.printers.values() if p.public
        ]
        return web.json_response({"email": caller.email, "printers": printers})

    async def index(self, request: web.Request) -> web.Response:
        await self.web_sender(request)
        return web.Response(text=_INDEX, content_type="text/html")


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

    async def start(_: web.Application) -> None:
        hub.start()

    async def stop(_: web.Application) -> None:
        await hub.shutdown()

    app.on_startup.append(start)
    app.on_shutdown.append(stop)
    return app
