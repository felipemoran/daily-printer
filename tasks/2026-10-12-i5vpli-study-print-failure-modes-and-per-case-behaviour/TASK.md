---
id: 2026-10-12-i5vpli-study-print-failure-modes-and-per-case-behaviour
title: Study print failure modes and per-case behaviour
status: pending
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: study
parent: null
scope: null
phase: null
---

## Description

Study every way a print job can fail, and decide how the system should behave in each case. The operator asked for this on 2026-10-12, after the paper-out question.

Current behaviour (code: `JobQueue.release`, `MAX_ATTEMPTS`, `DeviceHub`, `ERROR_PAUSE_SECONDS`):
- A device `error` reply, or no reply within 120 s, counts as one of 3 attempts and pauses that printer for 60 s.
- So a paper-out fails the job at the head of the queue after about 2 minutes, long before its expiry (1 h default).
- A printer that is offline (no device connected) holds its jobs until they expire. Offline time costs no attempts.
- A render failure is refused at intake (422 or 500); it never reaches the queue.

Cases to cover, at least:
- printer offline: device not connected, or device connected but USB printer unplugged;
- paper out, cover open, head too hot, cutter jam (what the printer can report over USB, if anything);
- device crash or network loss in the middle of a job (partial print);
- a reply timeout;
- server restart with jobs in flight;
- expiry while waiting.

Questions to answer:
- Which failures should cost an attempt, and which should only pause the printer?
- Should behaviour depend on the time of day: for example, hold jobs overnight, and fail fast during a workday?
- Who is told, and how: the admin interface, the sender, a notification?
- Can this printer (VID 0x6868, PID 0x0200) report paper status (ESC/POS `DLE EOT`)? Test it on the real hardware.

Output: a decision record in `docs/`, then implementation tasks.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
