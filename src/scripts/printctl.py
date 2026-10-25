"""
Admin command for the print server: send jobs, inspect the queue, and control printers.

The admin token comes from env PRINT_ADMIN_TOKEN or --token-file, never from the command line.

Examples:
  export PRINT_ADMIN_TOKEN=...
  uv run src/scripts/printctl.py send receipt samples/receipt-sample.json --printer home --expires 2h
  uv run src/scripts/printctl.py send template samples/templates/ticket.json --printer home
  uv run src/scripts/printctl.py send text samples/templates/build.json --printer home
  uv run src/scripts/printctl.py jobs --status queued
  uv run src/scripts/printctl.py show 3f9a2c1b
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import TextIO

DEFAULT_SERVER = "http://127.0.0.1:8787"
SERVER_ENV = "PRINT_SERVER_URL"
TOKEN_ENV = "PRINT_ADMIN_TOKEN"
# A receipt, template or text job starts a Chromium on the server, so intake can take a while.
TIMEOUT_SECONDS = 120
EXPIRY_UNITS = {"m": 60, "h": 3600, "d": 86400}
# The server refuses bodies over 10 MB; base64 adds a third, and the JSON around it needs a little room.
MAX_IMAGE_BYTES = (10 * 1024 * 1024 - 64 * 1024) // 4 * 3
SPARK = "▁▂▃▄▅▆▇█"
AGE_UNITS = [("s", 1, 60), ("min", 60, 60), ("h", 3600, 24), ("d", 86400, None)]
START_HINT = "Start it with: uv run src/scripts/print_server.py --config <config.toml>"


class Failure(Exception):
    """A failure to report on stderr, with an exit status. ``hint`` is printctl advice that follows the message."""

    def __init__(self, message: str, status: int = 1, *, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.hint = hint


# --- formatting -----------------------------------------------------------------------------------------------------

class Style:
    CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "cyan": "36"}

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    @classmethod
    def for_stream(cls, stream: TextIO) -> Style:
        isatty = getattr(stream, "isatty", None)
        return cls(bool(isatty and isatty()) and not os.environ.get("NO_COLOR"))

    def __call__(self, text: str, name: str | None) -> str:
        if not self.enabled or name is None:
            return text
        return f"\033[{self.CODES[name]}m{text}\033[0m"


STATUS_STYLE = {
    "queued": "yellow", "sending": "cyan", "printed": "green", "failed": "red", "expired": "dim", "cancelled": "dim",
}


def human_size(size: int | None) -> str:
    if size is None:
        return "-"
    if size < 1024:
        return f"{size} B"
    if round(size / 1024) < 1024:
        return f"{round(size / 1024)} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def paper(mm: float | None) -> str:
    return "-" if mm is None else f"{mm / 10:.1f} cm"


def age(at: float | None, now: float | None = None) -> str:
    """A relative time: ``3 min ago``, or ``in 2 h`` for a time in the future."""
    if at is None:
        return "-"
    now = time.time() if now is None else now
    delta = now - at
    seconds = abs(delta)
    if seconds < 10:
        return "just now"
    for name, size, limit in AGE_UNITS:
        count = round(seconds / size)
        if limit is None or count < limit:
            break
    amount = f"{count} {name}"
    return f"{amount} ago" if delta > 0 else f"in {amount}"


def local_time(at: float | None) -> str:
    return "-" if at is None else datetime.fromtimestamp(at).strftime("%Y-%m-%d %H:%M:%S")


def table(headers: list[str], rows: list[list[tuple[str, str | None]]], style: Style) -> str:
    """Aligned columns. Each cell is (text, style name); widths come from the plain text, so colour never skews them."""
    widths = [len(h) for h in headers]
    for row in rows:
        for index, (text, _) in enumerate(row):
            widths[index] = max(widths[index], len(text))
    # Padding inside a colour code survives rstrip, so the last column gets none.
    widths[-1] = 0

    def line(cells: list[tuple[str, str | None]]) -> str:
        return "  ".join(style(text.ljust(width), name) for (text, name), width in zip(cells, widths)).rstrip()

    return "\n".join([line([(h, "bold") for h in headers]), *map(line, rows)])


def fields(pairs: list[tuple[str, str]], style: Style) -> str:
    width = max(len(label) for label, _ in pairs)
    return "\n".join(f"{style(label.ljust(width), 'dim')}  {value}" for label, value in pairs)


def sparkline(counts: list[int]) -> str:
    peak = max(counts, default=0)
    if peak == 0:
        return SPARK[0] * len(counts)
    return "".join(SPARK[0] if count == 0 else SPARK[max(1, round(count / peak * (len(SPARK) - 1)))]
                   for count in counts)


# --- HTTP -----------------------------------------------------------------------------------------------------------

class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """urllib would follow a redirect with the Authorization header, and turn a POST into a GET."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        path = req.selector
        if path and newurl.endswith(path):
            raise Failure(f"The server answered HTTP {code} and redirected to {newurl[:-len(path)]}",
                          hint="; pass that URL with --server.")
        raise Failure(f"The server answered HTTP {code} and redirected to {newurl}", hint="; check --server.")


class Client:
    def __init__(self, server: str, token: str, *, timeout: float | None = None) -> None:
        self.server = server.rstrip("/")
        self._token = token
        self.timeout = TIMEOUT_SECONDS if timeout is None else timeout
        self._opener = urllib.request.build_opener(_RefuseRedirects)

    def __repr__(self) -> str:
        return f"Client({self.server!r})"

    def request(self, method: str, path: str, body: dict | None = None, *, expect: str = "application/json"):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self._token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            request = urllib.request.Request(self.server + path, data=data, headers=headers, method=method)
            with self._opener.open(request, timeout=self.timeout) as response:
                content_type = response.headers.get_content_type()
                payload = response.read()
        except urllib.error.HTTPError as error:
            raise self._http_error(error) from None
        except ValueError:
            raise Failure(f"{self.server} is not a valid server URL; use the form http://host:port") from None
        except TimeoutError:
            hint = " The request may have taken effect anyway; check `printctl jobs` before you retry."
            raise Failure(f"The server at {self.server} sent no answer within {self.timeout} s.",
                          hint=hint if method == "POST" else "") from None
        except (OSError, http.client.HTTPException) as error:
            reason = getattr(error, "reason", error)
            raise Failure(f"The print server is not reachable at {self.server} ({reason}).",
                          hint=f"\n{START_HINT}") from None
        if content_type != expect:
            raise Failure(f"The server at {self.server} sent {content_type}, not {expect}; is it the print server?")
        if expect != "application/json":
            return payload
        try:
            return json.loads(payload)
        except ValueError:
            raise Failure(f"The server at {self.server} sent invalid JSON; is it the print server?") from None

    def _http_error(self, error: urllib.error.HTTPError) -> Failure:
        try:
            message = json.loads(error.read())["error"]
        except (ValueError, KeyError, TypeError, OSError):
            message = None
        if message is None and 300 <= error.code < 400:
            location = error.headers.get("Location")
            target = f" to {location}" if location else ""
            return Failure(f"The server answered HTTP {error.code} and redirected{target}", hint="; check --server.")
        if message is None:
            return Failure(f"The server at {self.server} answered HTTP {error.code} ({error.reason}) without a print "
                           f"server error. The print server may be down behind a proxy or tunnel.",
                           hint=f"\n{START_HINT}")
        if error.code == 401:
            return Failure(f"{message} (HTTP 401).", hint=f" Check the admin token in {TOKEN_ENV} or --token-file.")
        return Failure(f"{message} (HTTP {error.code})")


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


# --- arguments ------------------------------------------------------------------------------------------------------

def expiry_seconds(text: str) -> int:
    match = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", text.lower())
    if match is None or int(match[1]) == 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a duration; use minutes, hours or days: 30m, 2h, 1d")
    return int(match[1]) * EXPIRY_UNITS[match[2]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="printctl",
        description="Control the print server: send jobs, inspect the queue, manage printers.",
        epilog=f"The admin token comes from env {TOKEN_ENV} or --token-file. "
               f"The server URL comes from --server, env {SERVER_ENV}, or {DEFAULT_SERVER}.",
    )
    parser.add_argument("--server", metavar="URL", help=f"the print server (default: ${SERVER_ENV} or {DEFAULT_SERVER})")
    parser.add_argument("--token-file", type=Path, metavar="PATH", help=f"a file with the admin token (default: ${TOKEN_ENV})")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    send = commands.add_parser("send", help="send a receipt, a template, native text or an image to a printer")
    send.add_argument("kind", choices=["receipt", "template", "text", "image"])
    send.add_argument("file", type=Path, help="receipt or template JSON payload (text: a template with a text mode), "
                                              "or an image file")
    send.add_argument("--printer", required=True, help="printer id")
    send.add_argument("--title", default="", help="a short label for the job list")
    send.add_argument("--expires", type=expiry_seconds, metavar="DURATION",
                      help="drop the job if it is not printed in time: 30m, 2h, 1d (server default: 1 h)")

    jobs = commands.add_parser("jobs", help="list jobs, newest first")
    jobs.add_argument("--printer", help="only this printer")
    jobs.add_argument("--status", help="only this status: queued, sending, printed, failed, expired, cancelled")
    jobs.add_argument("--limit", type=int, default=20, help="at most this many jobs (default: 20)")

    show = commands.add_parser("show", help="show a job, its artifact folder on the server and its event timeline")
    show.add_argument("id")

    image = commands.add_parser("image", help="save the rendered PNG of a job")
    image.add_argument("id")
    image.add_argument("-o", "--output", type=Path, required=True, metavar="FILE", help="where to write the PNG")

    cancel = commands.add_parser("cancel", help="cancel a queued or sending job")
    cancel.add_argument("id")

    clear = commands.add_parser("clear", help="cancel every queued and sending job of a printer")
    clear.add_argument("printer")

    reprint = commands.add_parser("reprint", help="queue a finished job again")
    reprint.add_argument("id")
    reprint.add_argument("--printer", help="print on this printer instead of the original one")

    move = commands.add_parser("move", help="move the queued jobs of one printer to another")
    move.add_argument("source", metavar="from")
    move.add_argument("target", metavar="to")

    commands.add_parser("printers", help="show each printer's connection and queue")
    commands.add_parser("stats", help="show print counts, paper use and hourly activity")
    return parser


def server_url(flag: str | None) -> str:
    return flag or os.environ.get(SERVER_ENV) or DEFAULT_SERVER


def admin_token(token_file: Path | None) -> str:
    token = _read_token(token_file)
    # A header cannot carry whitespace or non-ASCII; urllib would report it as a bad URL.
    if not re.fullmatch(r"[\x21-\x7e]+", token):
        where = f"the token file {token_file}" if token_file is not None else TOKEN_ENV
        raise Failure(f"The admin token in {where} has a space, a line break or a non-ASCII character.", 2)
    return token


def _read_token(token_file: Path | None) -> str:
    if token_file is not None:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise Failure(f"Cannot read the token file {token_file}: {error.strerror or error}", 2) from None
        if not token:
            raise Failure(f"The token file {token_file} is empty", 2)
        return token
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise Failure(f"No admin token. Set {TOKEN_ENV}, or pass --token-file with the path of a file that holds it.", 2)
    return token


# --- commands -------------------------------------------------------------------------------------------------------

def _job_line(job: dict) -> str:
    return (f"{job['kind']}, {paper(job['paper_mm'])}, {human_size(job['size_bytes'])}, "
            f"expires {age(job['expires_at'])}")


def cmd_send(args, client: Client, out: TextIO, style: Style) -> None:
    try:
        content = args.file.read_bytes()
    except OSError as error:
        raise Failure(f"Cannot read {args.file}: {error.strerror or error}") from None
    body = {"printer": args.printer, "kind": args.kind, "title": args.title}
    if args.expires is not None:
        body["expires_in"] = args.expires
    if args.kind in ("receipt", "template", "text"):
        try:
            payload = json.loads(content)
        except ValueError as error:
            raise Failure(f"{args.file} is not valid JSON: {error}") from None
        if not isinstance(payload, dict):
            raise Failure(f"{args.file} must hold a JSON object, the {args.kind} payload")
        body["payload"] = payload
    else:
        if len(content) > MAX_IMAGE_BYTES:
            raise Failure(f"{args.file} is {human_size(len(content))}; the server takes images up to "
                          f"{human_size(MAX_IMAGE_BYTES)}. Shrink it first: the printer prints 384 dots wide.")
        body["image"] = base64.b64encode(content).decode("ascii")
    job = client.request("POST", "/api/jobs", body)
    print(f"Queued {style(job['id'], 'bold')} for {job['printer']}: {_job_line(job)}", file=out)


def cmd_jobs(args, client: Client, out: TextIO, style: Style) -> None:
    query = {"limit": args.limit}
    if args.printer:
        query["printer"] = args.printer
    if args.status:
        query["status"] = args.status
    jobs = client.request("GET", "/api/jobs?" + urllib.parse.urlencode(query))["jobs"]
    if not jobs:
        print("No jobs match.", file=out)
        return
    rows = [[
        (job["id"], None), (job["printer"], None), (job["status"], STATUS_STYLE.get(job["status"])),
        (job["kind"], None), (job["title"] or "-", None), (job["source"], None),
        (paper(job["paper_mm"]), None), (human_size(job["size_bytes"]), None), (age(job["created_at"]), "dim"),
    ] for job in jobs]
    headers = ["ID", "PRINTER", "STATUS", "KIND", "TITLE", "SOURCE", "PAPER", "SIZE", "CREATED"]
    print(table(headers, rows, style), file=out)


def cmd_show(args, client: Client, out: TextIO, style: Style) -> None:
    job = client.request("GET", f"/api/jobs/{_quote(args.id)}")
    status = style(job["status"], STATUS_STYLE.get(job["status"]))
    pairs = [
        ("id", job["id"]),
        ("printer", job["printer"]),
        ("status", f"{status} (attempt {job['attempts']})" if job["attempts"] else status),
        ("kind", job["kind"]),
        ("title", job["title"] or "-"),
        ("source", f"{job['source']} via {job['ingress']}"),
        ("size", f"{job['width']} x {job['height']} dots, {paper(job['paper_mm'])} of paper, "
                 f"{human_size(job['size_bytes'])} in {job['frames']} frames"),
        ("rendered in", f"{job['render_ms']} ms"),
        ("created", f"{local_time(job['created_at'])} ({age(job['created_at'])})"),
        ("expires", f"{local_time(job['expires_at'])} ({age(job['expires_at'])})"),
        ("artifacts", job["artifacts"] or style("missing on the server", "red")),
    ]
    if job["printed_at"] is not None:
        pairs.append(("printed", f"{local_time(job['printed_at'])} ({age(job['printed_at'])})"))
    print(fields(pairs, style), file=out)
    print(file=out)
    rows = [[(local_time(event["at"]), "dim"), (event["event"], STATUS_STYLE.get(event["event"])),
             (event["detail"] or "", None)] for event in job["events"]]
    print(table(["TIME", "EVENT", "DETAIL"], rows, style), file=out)


def cmd_image(args, client: Client, out: TextIO, style: Style) -> None:
    png = client.request("GET", f"/api/jobs/{_quote(args.id)}/image", expect="image/png")
    try:
        args.output.write_bytes(png)
    except OSError as error:
        raise Failure(f"Cannot write {args.output}: {error.strerror or error}") from None
    print(f"Saved the image of {args.id} to {args.output} ({human_size(len(png))})", file=out)


def cmd_cancel(args, client: Client, out: TextIO, style: Style) -> None:
    job = client.request("POST", f"/api/jobs/{_quote(args.id)}/cancel")
    print(f"Cancelled {job['id']} on {job['printer']}", file=out)


def cmd_clear(args, client: Client, out: TextIO, style: Style) -> None:
    count = client.request("POST", f"/api/printers/{_quote(args.printer)}/clear")["cancelled"]
    print(f"Cancelled {count} queued {'job' if count == 1 else 'jobs'} on {args.printer}", file=out)


def cmd_reprint(args, client: Client, out: TextIO, style: Style) -> None:
    body = {"printer": args.printer} if args.printer else {}
    job = client.request("POST", f"/api/jobs/{_quote(args.id)}/reprint", body)
    print(f"Queued {style(job['id'], 'bold')} for {job['printer']} as a reprint of {args.id}: {_job_line(job)}",
          file=out)


def cmd_move(args, client: Client, out: TextIO, style: Style) -> None:
    count = client.request("POST", f"/api/printers/{_quote(args.source)}/move", {"to": args.target})["moved"]
    print(f"Moved {count} queued {'job' if count == 1 else 'jobs'} from {args.source} to {args.target}", file=out)


def _printer_state(printer: dict) -> tuple[str, str]:
    if printer.get("paused_until"):
        return f"paused until {datetime.fromtimestamp(printer['paused_until']):%H:%M}", "yellow"
    if printer["online"]:
        return "online", "green"
    return "offline", "red"


def cmd_printers(args, client: Client, out: TextIO, style: Style) -> None:
    printers = client.request("GET", "/api/printers")["printers"]
    if not printers:
        print("No printers in the server config.", file=out)
        return
    rows = []
    for printer in printers:
        current = printer["current_job"]
        job = f"{current['id']} ({current['frames_sent']}/{current['frames']})" if current else "-"
        latency = printer["latency_ms"]
        rows.append([
            (printer["id"], None), (printer["name"], None), (printer["place"] or "-", None),
            _printer_state(printer), (str(printer["queued"]), None), (str(printer["printed_today"]), None),
            (job, None), (age(printer["last_seen"]), "dim"),
            ("-" if latency is None else f"{latency:.0f} ms", None), (printer["route"] or "-", None),
            (printer["client_version"] or "-", None), ("yes" if printer["public"] else "no", None),
        ])
    headers = ["ID", "NAME", "PLACE", "STATE", "QUEUED", "TODAY", "PRINTING", "LAST SEEN", "LATENCY", "ROUTE",
               "VERSION", "PUBLIC"]
    print(table(headers, rows, style), file=out)


def cmd_stats(args, client: Client, out: TextIO, style: Style) -> None:
    stats = client.request("GET", "/api/stats")
    median = stats["median_job_seconds"]
    pairs = [
        ("printed today", str(stats["printed_today"])),
        ("paper today", paper(stats["paper_today_mm"])),
        ("queued", str(stats["queued"])),
        ("failed (24 h)", str(stats["failed_24h"])),
        ("median job (24 h)", "-" if median is None else f"{median:.1f} s from intake to print"),
    ]
    print(fields(pairs, style), file=out)
    hourly = stats["hourly"]
    if hourly:
        print(file=out)
        rows = [[(name, None), (sparkline(counts), "cyan"), (str(sum(counts)), None)]
                for name, counts in sorted(hourly.items())]
        print(table(["PRINTER", "LAST 24 H (OLDEST TO NOW)", "PRINTED"], rows, style), file=out)


COMMANDS = {
    "send": cmd_send, "jobs": cmd_jobs, "show": cmd_show, "image": cmd_image, "cancel": cmd_cancel,
    "clear": cmd_clear, "reprint": cmd_reprint, "move": cmd_move, "printers": cmd_printers, "stats": cmd_stats,
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    out = sys.stdout
    try:
        client = Client(server_url(args.server), admin_token(args.token_file))
        COMMANDS[args.command](args, client, out, Style.for_stream(out))
    except Failure as failure:
        print(f"printctl: {failure.message}{failure.hint}", file=sys.stderr)
        return failure.status
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
