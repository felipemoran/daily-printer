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
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions

- 2026-10-12T15:29:00+00:00: Operator decision 2026-10-12: cancel of a job in sending stays allowed. If the device then confirms it, the job becomes printed (with an event that says it printed after the cancel), so the admin page never shows cancelled for a ticket on paper.
