---
id: 2026-10-12-enfk3k-queue-robustness-and-doc-fixes-from-the-schema-rev
title: Queue robustness and doc fixes from the schema review
status: in-progress
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: fix
parent: null
scope: null
phase: implementing
---

## Description

Found 2026-10-12 while documenting the schema (artifact https://claude.ai/artifact/CXL4KRu3umoSesuRNydFmb). Code: `src/job_queue.py`. Do after task axvgf8 lands, because it changes the same file.

Defects:
- `cancel` and `clear` accept a job in `sending`. The device can still print it; `confirm` then does nothing, so the admin page shows `cancelled` for a ticket that is on paper. Behaviour choice for the operator: refuse cancel while sending, or record `printed` when the confirmation arrives.
- No WAL and Python's default 5 s busy timeout. A read transaction held open by another program (for example the sqlite3 shell during a backup) can make server calls fail with "database is locked".
- No schema version (`PRAGMA user_version`) and no migration step. Any change to an existing table needs one once a real database exists.
- `job_events.job_id REFERENCES jobs(id)` is not enforced: `PRAGMA foreign_keys` is never turned on.

Docs that disagree with the code (`docs/planning-print-system-architecture.md`, "Job lifecycle" and "Interfaces"):
- Expiry is lazy (`JobQueue._expire` runs at the start of other queue calls); "dropped" only clears the ESC/POS bytes; a late confirmation of a `sending` job still marks it printed.
- An unconfirmed job is released at once, not "when the device reconnects".
- The printer state lists 15 fields; 7 are stored, and `online`, `current_job` and `paused_until` live in `DeviceHub` memory.
- `paper_mm` is computed (`height / 8`), not stored.

Notes, no action unless measured:
- Unfiltered `JobQueue.jobs`, the all-printers printed query in `stats()` and the 24-hour failed count scan whole tables; with forever retention these grow with history.
- A printer removed from the config keeps its row and its queued jobs until they expire.
- A job on its third attempt that is also past expiry becomes `failed`, not `expired`.

## Acceptance check

<!-- AC:BEGIN -->
- [x] A job cancelled while sending, then confirmed, ends `printed` with a `printed` event "after the cancel", through `JobQueue` (cancel and clear) and through the device hub: `test_a_job_cancelled_while_sending_and_then_confirmed_is_printed`, `test_a_job_cancelled_while_sending_that_the_device_prints_is_printed`.
- [x] A device `error` for a job cancelled while sending leaves it cancelled and not retried: `test_a_job_cancelled_while_sending_that_the_device_fails_stays_cancelled`.
- [x] WAL is on, and a reader holding a transaction does not make `add` fail: `test_a_reader_holding_a_transaction_does_not_block_a_write`.
- [x] Schema version: new, migrated from 0 (with and without `png`), refused when newer: `SchemaVersionTest`.
- [x] Foreign keys are on: `test_an_event_for_a_missing_job_is_refused`.
- [x] A failed COMMIT rolls back and deletes the renamed folder, with production connection settings: `test_a_failed_commit_removes_the_renamed_folder_and_stores_no_job`.
- [x] Docs match the code: "Job lifecycle", "HTTP API", "Job record", "Job storage" and "Printer state" in `docs/planning-print-system-architecture.md`.
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T16:26:44+00:00: Fixed the queue findings. Cancel while sending stays allowed (operator decision): confirm now also accepts a cancelled job and marks it printed with the event detail 'after the cancel'; a device error for such a job leaves it cancelled, because _release only acts on a job in sending. The connection uses WAL and a 10 s busy timeout: under WAL a reader never blocks a write, so the timeout covers only another writer, and the wait blocks the event loop, so it stays far below the 60 s device receive timeout. Foreign keys are on. PRAGMA user_version holds the schema version (1): a new database gets it, version 0 with tables runs the ordered _MIGRATIONS steps, a newer version is refused (SchemaTooNew) before the file is touched. The 0 to 1 step drops the unused png column, so every version-1 database has one shape for later steps; no deployed database holds png data. The failed-COMMIT test now forces the failure with a deferred foreign key violation from a temp trigger, because under WAL a held read no longer fails COMMIT. Docs: architecture Job lifecycle, HTTP API cancel row, Job record, Job storage (SQLite settings, backups with -wal and -shm), Printer state; printctl cancel and clear help and rows; the deploy file table. Not changed: docs/reference-print-queue-schema.html, a review snapshot that was already stale (png column, prune) and now also states the old WAL, foreign key, versioning and cancel facts.

## Decisions

- 2026-10-12T15:29:00+00:00: Operator decision 2026-10-12: cancel of a job in sending stays allowed. If the device then confirms it, the job becomes printed (with an event that says it printed after the cancel), so the admin page never shows cancelled for a ticket on paper.
