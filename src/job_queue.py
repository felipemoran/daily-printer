"""Print jobs waiting for their printer, stored in SQLite so a restart keeps them."""

from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MAX_ATTEMPTS = 3
DEFAULT_EXPIRY_SECONDS = 3600


class Status(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    PRINTED = "printed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Job:
    id: str
    printer: str
    status: Status
    attempts: int
    created_at: float
    expires_at: float
    data: bytes | None = None


_COLUMNS = "id, printer, status, attempts, created_at, expires_at"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    printer TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    data BLOB
)
"""


def _job(row: tuple) -> Job:
    return Job(row[0], row[1], Status(row[2]), *row[3:])


class JobQueue:
    def __init__(self, path: Path | str) -> None:
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.execute(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def add(self, printer: str, data: bytes, *, expires_in: float = DEFAULT_EXPIRY_SECONDS,
            now: float | None = None) -> Job:
        now = time.time() if now is None else now
        row = self._db.execute(
            f"INSERT INTO jobs (id, printer, status, created_at, expires_at, data) VALUES (?, ?, ?, ?, ?, ?)"
            f" RETURNING {_COLUMNS}",
            (secrets.token_hex(4), printer, Status.QUEUED, now, now + expires_in, data),
        ).fetchone()
        return _job(row)

    def take(self, printer: str, *, now: float | None = None) -> Job | None:
        """Mark the oldest deliverable job for ``printer`` as sending and return it with its data."""
        now = self._expire(now)
        row = self._db.execute(
            f"UPDATE jobs SET status = ?, attempts = attempts + 1"
            f" WHERE id = (SELECT id FROM jobs WHERE printer = ? AND status = ? ORDER BY created_at, rowid LIMIT 1)"
            f" RETURNING {_COLUMNS}, data",
            (Status.SENDING, printer, Status.QUEUED),
        ).fetchone()
        return _job(row) if row else None

    def confirm(self, job_id: str) -> None:
        self._finish(job_id, Status.PRINTED, only_if=Status.SENDING)

    def release(self, job_id: str, *, now: float | None = None) -> None:
        """Return an unconfirmed job to the queue, unless it used its last attempt or expired."""
        now = time.time() if now is None else now
        row = self._db.execute(
            "SELECT attempts, expires_at FROM jobs WHERE id = ? AND status = ?", (job_id, Status.SENDING)
        ).fetchone()
        if row is None:
            return
        attempts, expires_at = row
        if attempts >= MAX_ATTEMPTS:
            self._finish(job_id, Status.FAILED)
        elif expires_at <= now:
            self._finish(job_id, Status.EXPIRED)
        else:
            self._db.execute("UPDATE jobs SET status = ? WHERE id = ?", (Status.QUEUED, job_id))

    def release_all(self, *, now: float | None = None) -> None:
        """Release every job left in sending, e.g. by a server that stopped mid-delivery."""
        ids = [r[0] for r in self._db.execute("SELECT id FROM jobs WHERE status = ?", (Status.SENDING,))]
        for job_id in ids:
            self.release(job_id, now=now)

    def cancel(self, job_id: str) -> bool:
        return self._finish(job_id, Status.CANCELLED, only_if=(Status.QUEUED, Status.SENDING)) > 0

    def clear(self, printer: str) -> int:
        return self._db.execute(
            "UPDATE jobs SET status = ?, data = NULL WHERE printer = ? AND status IN (?, ?)",
            (Status.CANCELLED, printer, Status.QUEUED, Status.SENDING),
        ).rowcount

    def jobs(self, printer: str | None = None, *, now: float | None = None) -> list[Job]:
        self._expire(now)
        where, args = ("WHERE printer = ?", (printer,)) if printer else ("", ())
        rows = self._db.execute(f"SELECT {_COLUMNS} FROM jobs {where} ORDER BY created_at, rowid", args)
        return [_job(row) for row in rows]

    def _expire(self, now: float | None) -> float:
        now = time.time() if now is None else now
        self._db.execute(
            "UPDATE jobs SET status = ?, data = NULL WHERE status = ? AND expires_at <= ?",
            (Status.EXPIRED, Status.QUEUED, now),
        )
        return now

    def _finish(self, job_id: str, status: Status, *, only_if: Status | tuple[Status, ...] = ()) -> int:
        allowed = (only_if,) if isinstance(only_if, Status) else only_if
        guard = f" AND status IN ({', '.join('?' * len(allowed))})" if allowed else ""
        return self._db.execute(
            f"UPDATE jobs SET status = ?, data = NULL WHERE id = ?{guard}", (status, job_id, *allowed)
        ).rowcount
