"""Print jobs, their events, printer state and stats, stored in SQLite so a restart keeps them."""

from __future__ import annotations

import secrets
import shutil
import sqlite3
import statistics
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from enum import StrEnum
from pathlib import Path

from printer import DOTS_PER_MM

MAX_ATTEMPTS = 3
DEFAULT_EXPIRY_SECONDS = 3600
FRAME_SIZE = 4096
DAY_SECONDS = 86400
HOUR_SECONDS = 3600
ID_TRIES = 5
# The wait for another writer blocks the server's event loop: keep it far below the 60 s device receive timeout.
BUSY_TIMEOUT_SECONDS = 10.0


class JobNotFinal(ValueError):
    """The job is still queued or sending."""


class Status(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    PRINTED = "printed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Event(StrEnum):
    RECEIVED = "received"
    RENDERED = "rendered"
    SENDING = "sending"
    SENT = "sent"
    PRINTED = "printed"
    RELEASED = "released"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    MOVED = "moved"
    REPRINTED = "reprinted"


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    at: float
    event: Event
    detail: str | None


@dataclass(frozen=True)
class Job:
    id: str
    printer: str
    kind: str
    title: str
    source: str
    ingress: str
    status: Status
    attempts: int
    created_at: float
    expires_at: float
    render_ms: int
    width: int
    height: int
    paper_mm: float
    size_bytes: int
    frames: int
    sent_at: float | None
    printed_at: float | None
    data: bytes | None = None
    events: tuple[JobEvent, ...] = ()


@dataclass(frozen=True)
class PrinterState:
    id: str
    last_seen: float | None = None
    connected_since: float | None = None
    address: str | None = None
    route: str | None = None
    latency_ms: float | None = None
    client_version: str | None = None


PRINTER_FIELDS = ("last_seen", "connected_since", "address", "route", "latency_ms", "client_version")


@dataclass(frozen=True)
class Stats:
    printed_today: int
    queued: int
    failed_24h: int
    median_job_seconds: float | None
    paper_today_mm: float
    hourly: dict[str, list[int]] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceActivity:
    ingress: str
    source: str
    jobs_today: int
    last_job: Job


_COLUMNS = (
    f"id, printer, kind, title, source, ingress, status, attempts, created_at, expires_at,"
    f" render_ms, width, height, height * 1.0 / {DOTS_PER_MM}, size_bytes, frames, sent_at, printed_at"
)

_SCHEMA = (
    """CREATE TABLE jobs (
        id TEXT PRIMARY KEY,
        printer TEXT NOT NULL,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        source TEXT NOT NULL,
        ingress TEXT NOT NULL,
        status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        render_ms INTEGER NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        size_bytes INTEGER NOT NULL,
        frames INTEGER NOT NULL,
        sent_at REAL,
        printed_at REAL,
        data BLOB
    )""",
    "CREATE INDEX jobs_printer_status ON jobs (printer, status)",
    "CREATE INDEX jobs_queued_expiry ON jobs (expires_at) WHERE status = 'queued'",
    "CREATE INDEX jobs_source ON jobs (ingress, source, created_at)",
    """CREATE TABLE job_events (
        id INTEGER PRIMARY KEY,
        job_id TEXT NOT NULL REFERENCES jobs (id),
        at REAL NOT NULL,
        event TEXT NOT NULL,
        detail TEXT
    )""",
    "CREATE INDEX job_events_job ON job_events (job_id)",
    """CREATE TABLE printers (
        id TEXT PRIMARY KEY,
        last_seen REAL,
        connected_since REAL,
        address TEXT,
        route TEXT,
        latency_ms REAL,
        client_version TEXT
    )""",
)


def _drop_png(db: sqlite3.Connection) -> None:
    if any(column[1] == "png" for column in db.execute("PRAGMA table_info(jobs)")):
        db.execute("ALTER TABLE jobs DROP COLUMN png")


# Step n takes a database from version n to n + 1. Version 0 is the schema from before versioning.
_MIGRATIONS: tuple[Callable[[sqlite3.Connection], None], ...] = (_drop_png,)
SCHEMA_VERSION = len(_MIGRATIONS)


class SchemaTooNew(RuntimeError):
    """The database was written by a newer server."""


def _job(row: tuple) -> Job:
    return Job(*row[:6], Status(row[6]), *row[7:])


@contextmanager
def _placing(artifacts: Path | None) -> Iterator[Callable[[str], None]]:
    """Yields ``place(job_id)``, which renames ``artifacts`` to the job id inside the caller's transaction.

    The folder is deleted when the transaction fails after the rename. A crash after it leaves a folder no job names.
    """
    placed = []

    def place(job_id: str) -> None:
        if artifacts is not None:
            placed.append(artifacts.rename(artifacts.with_name(job_id)))

    try:
        yield place
    except BaseException:
        for folder in placed:
            shutil.rmtree(folder, ignore_errors=True)
        raise


def _new_id() -> str:
    return secrets.token_hex(4)


def _local_midnight(now: float, tz: tzinfo | None) -> float:
    # A naive datetime makes timestamp() use the system zone, including its DST rule for that day.
    moment = datetime.fromtimestamp(now, tz)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class JobQueue:
    def __init__(self, path: Path | str) -> None:
        self._db = sqlite3.connect(path, isolation_level=None, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            self._open()
        except BaseException:
            self._db.close()
            raise

    def _open(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise SchemaTooNew(f"its schema version is {version}, and this server knows versions up to"
                               f" {SCHEMA_VERSION}. Run a newer server, or restore a backup from before the upgrade.")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA foreign_keys = ON")
        with self._transaction():
            if self._db.execute("SELECT 1 FROM sqlite_master WHERE name = 'jobs'").fetchone() is None:
                for statement in _SCHEMA:
                    self._db.execute(statement)
            else:
                for step in _MIGRATIONS[version:]:
                    step(self._db)
            self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    def add(self, printer: str, data: bytes, *, kind: str, title: str, source: str, ingress: str,
            width: int, height: int, render_ms: int, artifacts: Path | None = None,
            expires_in: float = DEFAULT_EXPIRY_SECONDS, now: float | None = None) -> Job:
        """``artifacts``, a staged folder, becomes ``<its parent>/<job id>`` before the insert commits."""
        now = time.time() if now is None else now
        with _placing(artifacts) as place, self._transaction():
            job = self._insert(printer, data, kind=kind, title=title, source=source, ingress=ingress, width=width,
                               height=height, render_ms=render_ms, expires_at=now + expires_in, now=now)
            self._event(job.id, now, Event.RECEIVED, f"{source} via {ingress}")
            self._event(job.id, now, Event.RENDERED, f"{width}x{height} dots in {render_ms} ms")
            place(job.id)
        return job

    def take(self, printer: str, *, now: float | None = None) -> Job | None:
        """Mark the oldest deliverable job for ``printer`` as sending and return it with its data."""
        with self._transaction():
            now = self._expire(now)
            row = self._db.execute(
                f"UPDATE jobs SET status = ?, attempts = attempts + 1"
                f" WHERE id = (SELECT id FROM jobs WHERE printer = ? AND status = ? ORDER BY created_at, rowid LIMIT 1)"
                f" RETURNING {_COLUMNS}, data",
                (Status.SENDING, printer, Status.QUEUED),
            ).fetchone()
            if row is None:
                return None
            job = _job(row)
            self._event(job.id, now, Event.SENDING, f"attempt {job.attempts}")
        return job

    def mark_sent(self, job_id: str, *, now: float | None = None) -> bool:
        """Record that the last frame of a job in sending went out."""
        now = time.time() if now is None else now
        with self._transaction():
            changed = self._db.execute(
                "UPDATE jobs SET sent_at = ? WHERE id = ? AND status = ?", (now, job_id, Status.SENDING)
            ).rowcount
            if changed:
                self._event(job_id, now, Event.SENT)
        return changed > 0

    def confirm(self, job_id: str, *, now: float | None = None) -> None:
        """Mark the job the device printed as printed, also when it was cancelled while sending."""
        now = time.time() if now is None else now
        with self._transaction():
            row = self._db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None or row[0] not in (Status.SENDING, Status.CANCELLED):
                return
            detail = "after the cancel" if row[0] == Status.CANCELLED else None
            self._finish(job_id, Status.PRINTED, now, detail=detail)
            self._db.execute("UPDATE jobs SET printed_at = ? WHERE id = ?", (now, job_id))

    def release(self, job_id: str, *, detail: str | None = None, now: float | None = None) -> None:
        """Return an unconfirmed job to the queue, unless it used its last attempt or expired."""
        now = time.time() if now is None else now
        with self._transaction():
            self._release(job_id, detail, now)

    def release_all(self, *, now: float | None = None) -> None:
        """Release every job left in sending, e.g. by a server that stopped mid-delivery."""
        now = time.time() if now is None else now
        with self._transaction():
            ids = [r[0] for r in self._db.execute("SELECT id FROM jobs WHERE status = ?", (Status.SENDING,))]
            for job_id in ids:
                self._release(job_id, None, now)

    def cancel(self, job_id: str, *, now: float | None = None) -> bool:
        with self._transaction():
            now = self._expire(now)
            return self._finish(job_id, Status.CANCELLED, now, only_if=(Status.QUEUED, Status.SENDING))

    def clear(self, printer: str, *, now: float | None = None) -> int:
        with self._transaction():
            now = self._expire(now)
            ids = [r[0] for r in self._db.execute(
                "UPDATE jobs SET status = ?, data = NULL WHERE printer = ? AND status IN (?, ?) RETURNING id",
                (Status.CANCELLED, printer, Status.QUEUED, Status.SENDING),
            ).fetchall()]
            for job_id in ids:
                self._event(job_id, now, Event.CANCELLED)
        return len(ids)

    def move(self, from_printer: str, to_printer: str, *, now: float | None = None) -> int:
        """Move the queued jobs of one printer to another. Jobs in sending stay where they are."""
        with self._transaction():
            now = self._expire(now)
            ids = [r[0] for r in self._db.execute(
                "UPDATE jobs SET printer = ? WHERE printer = ? AND status = ? RETURNING id",
                (to_printer, from_printer, Status.QUEUED),
            ).fetchall()]
            for job_id in ids:
                self._event(job_id, now, Event.MOVED, f"{from_printer} -> {to_printer}")
        return len(ids)

    def reprint(self, job_id: str, printer: str, data: bytes, *, source: str, ingress: str,
                artifacts: Path | None = None, now: float | None = None) -> Job | None:
        """Queue a copy of a finished job that sends ``data``. None when the job is unknown.

        ``artifacts``: as for ``add``.
        """
        with _placing(artifacts) as place, self._transaction():
            now = self._expire(now)
            row = self._db.execute(
                "SELECT status, kind, title, width, height, render_ms, expires_at - created_at"
                " FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            status, kind, title, width, height, render_ms, lifetime = row
            if status in (Status.QUEUED, Status.SENDING):
                raise JobNotFinal(f"job {job_id} is still {status}")
            job = self._insert(printer, data, kind=kind, title=title, source=source, ingress=ingress, width=width,
                               height=height, render_ms=render_ms, expires_at=now + lifetime, now=now)
            self._event(job.id, now, Event.RECEIVED, f"{source} via {ingress}, reprint of {job_id}")
            self._event(job.id, now, Event.RENDERED, f"{width}x{height} dots, the bytes of {job_id}")
            self._event(job_id, now, Event.REPRINTED, job.id)
            place(job.id)
        return job

    def job(self, job_id: str, *, now: float | None = None) -> Job | None:
        """The job with its events, without its data."""
        with self._transaction():
            self._expire(now)
            row = self._db.execute(f"SELECT {_COLUMNS} FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            events = tuple(
                JobEvent(job_id, at, Event(event), detail)
                for at, event, detail in self._db.execute(
                    "SELECT at, event, detail FROM job_events WHERE job_id = ? ORDER BY id", (job_id,)
                )
            )
        return _job(row + (None, events))

    def jobs(self, printer: str | None = None, status: Status | None = None, *, limit: int = 100,
             now: float | None = None) -> list[Job]:
        """Job summaries, newest first, without data or events."""
        conditions, args = [], []
        if printer is not None:
            conditions.append("printer = ?")
            args.append(printer)
        if status is not None:
            conditions.append("status = ?")
            args.append(Status(status))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._transaction():
            self._expire(now)
            rows = self._db.execute(
                f"SELECT {_COLUMNS} FROM jobs {where} ORDER BY created_at DESC, rowid DESC LIMIT ?", (*args, limit)
            ).fetchall()
        return [_job(row) for row in rows]

    def update_printer_state(self, printer_id: str, **fields: float | str | None) -> None:
        """Set the given fields of a printer's state, adding the printer when it is new."""
        unknown = set(fields) - set(PRINTER_FIELDS)
        if unknown:
            raise ValueError(f"unknown printer state fields: {', '.join(sorted(unknown))}")
        names = list(fields)
        updates = ", ".join(f"{name} = excluded.{name}" for name in names) or "id = id"
        self._db.execute(
            f"INSERT INTO printers (id{''.join(', ' + n for n in names)})"
            f" VALUES (?{', ?' * len(names)}) ON CONFLICT (id) DO UPDATE SET {updates}",
            (printer_id, *fields.values()),
        )

    def printer_state(self, printer_id: str) -> PrinterState | None:
        row = self._db.execute(
            f"SELECT id, {', '.join(PRINTER_FIELDS)} FROM printers WHERE id = ?", (printer_id,)
        ).fetchone()
        return PrinterState(*row) if row else None

    def stats(self, printer: str | None = None, *, now: float | None = None, tz: tzinfo | None = None) -> Stats:
        """Aggregates for all printers, or for one. "Today" starts at midnight in ``tz``, the system zone by default."""
        with self._transaction():
            now = self._expire(now)
        midnight = _local_midnight(now, tz)
        day_start = now - DAY_SECONDS
        only, args = ("AND printer = ?", (printer,)) if printer is not None else ("", ())

        printed = self._db.execute(
            f"SELECT printer, created_at, printed_at, height FROM jobs"
            f" WHERE status = ? AND printed_at >= ? AND printed_at <= ? {only}",
            (Status.PRINTED, min(midnight, day_start), now, *args),
        ).fetchall()
        today = [row for row in printed if row[2] >= midnight]
        last_day = [row for row in printed if row[2] > day_start]

        queued = self._db.execute(
            f"SELECT COUNT(*) FROM jobs WHERE status = ? {only}", (Status.QUEUED, *args)
        ).fetchone()[0]
        failed = self._db.execute(
            f"SELECT COUNT(*) FROM job_events JOIN jobs ON jobs.id = job_events.job_id"
            f" WHERE event = ? AND at > ? AND at <= ? {only}",
            (Event.FAILED, day_start, now, *args),
        ).fetchone()[0]

        if printer is None:
            names = [r[0] for r in self._db.execute("SELECT printer FROM jobs UNION SELECT id FROM printers")]
        else:
            names = [printer]
        hourly = {name: [0] * 24 for name in sorted(names)}
        for name, _, printed_at, _ in last_day:
            hourly[name][23 - int((now - printed_at) // HOUR_SECONDS)] += 1

        return Stats(
            printed_today=len(today),
            queued=queued,
            failed_24h=failed,
            median_job_seconds=statistics.median(p - c for _, c, p, _ in last_day) if last_day else None,
            paper_today_mm=sum(height for *_, height in today) / DOTS_PER_MM,
            hourly=hourly,
        )

    def activity(self, ingresses: tuple[str, ...], *, now: float | None = None,
                 tz: tzinfo | None = None) -> list[SourceActivity]:
        """Per (ingress, source) among ``ingresses``: jobs created today and the newest job, newest first."""
        if not ingresses:
            return []
        now = time.time() if now is None else now
        rows = self._db.execute(
            f"SELECT * FROM (SELECT {_COLUMNS},"
            f" ROW_NUMBER() OVER (PARTITION BY ingress, source ORDER BY created_at DESC, rowid DESC) AS rank,"
            f" SUM(created_at >= ? AND created_at <= ?) OVER (PARTITION BY ingress, source) AS today"
            f" FROM jobs WHERE ingress IN ({', '.join('?' * len(ingresses))}) AND created_at <= ?)"
            f" WHERE rank = 1 ORDER BY created_at DESC",
            (_local_midnight(now, tz), now, *ingresses, now),
        ).fetchall()
        return [SourceActivity(row[5], row[4], row[-1], _job(row[:-2])) for row in rows]

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            # A failed COMMIT can leave the transaction open; a later COMMIT would then store it.
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _insert(self, printer: str, data: bytes, *, kind: str, title: str, source: str, ingress: str,
                width: int, height: int, render_ms: int, expires_at: float, now: float) -> Job:
        for _ in range(ID_TRIES):
            try:
                row = self._db.execute(
                    f"INSERT INTO jobs (id, printer, kind, title, source, ingress, status, created_at, expires_at,"
                    f" render_ms, width, height, size_bytes, frames, data)"
                    f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING {_COLUMNS}",
                    (_new_id(), printer, kind, title, source, ingress, Status.QUEUED, now, expires_at,
                     render_ms, width, height, len(data), -(-len(data) // FRAME_SIZE), data),
                ).fetchone()
            except sqlite3.IntegrityError as error:
                if error.sqlite_errorname != "SQLITE_CONSTRAINT_PRIMARYKEY":
                    raise
                continue
            return _job(row)
        raise RuntimeError(f"no free job id after {ID_TRIES} tries")

    def _release(self, job_id: str, detail: str | None, now: float) -> None:
        row = self._db.execute(
            "SELECT attempts, expires_at FROM jobs WHERE id = ? AND status = ?", (job_id, Status.SENDING)
        ).fetchone()
        if row is None:
            return
        attempts, expires_at = row
        if attempts >= MAX_ATTEMPTS:
            self._finish(job_id, Status.FAILED, now, detail=detail)
        elif expires_at <= now:
            self._finish(job_id, Status.EXPIRED, now, detail=detail)
        else:
            self._db.execute("UPDATE jobs SET status = ? WHERE id = ?", (Status.QUEUED, job_id))
            self._event(job_id, now, Event.RELEASED, detail)

    def _expire(self, now: float | None) -> float:
        now = time.time() if now is None else now
        expired = self._db.execute(
            "UPDATE jobs SET status = ?, data = NULL WHERE status = ? AND expires_at <= ? RETURNING id, expires_at",
            (Status.EXPIRED, Status.QUEUED, now),
        ).fetchall()
        for job_id, expires_at in expired:
            self._event(job_id, expires_at, Event.EXPIRED)
        return now

    def _finish(self, job_id: str, status: Status, now: float, *, only_if: Status | tuple[Status, ...] = (),
                detail: str | None = None) -> bool:
        allowed = (only_if,) if isinstance(only_if, Status) else only_if
        guard = f" AND status IN ({', '.join('?' * len(allowed))})" if allowed else ""
        changed = self._db.execute(
            f"UPDATE jobs SET status = ?, data = NULL WHERE id = ?{guard}", (status, job_id, *allowed)
        ).rowcount
        if changed:
            self._event(job_id, now, Event(status.value), detail)
        return changed > 0

    def _event(self, job_id: str, at: float, event: Event, detail: str | None = None) -> None:
        self._db.execute(
            "INSERT INTO job_events (job_id, at, event, detail) VALUES (?, ?, ?, ?)", (job_id, at, event, detail)
        )
