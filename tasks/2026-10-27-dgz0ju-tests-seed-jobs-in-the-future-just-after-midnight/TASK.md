---
id: 2026-10-27-dgz0ju-tests-seed-jobs-in-the-future-just-after-midnight
title: Tests seed jobs in the future just after midnight
status: done
priority: 1
created_date: 2026-10-27
dependencies: []
labels: []
type: fix
parent: null
scope: null
phase: null
---

## Description

First CI run (PR 4, run 40423386396) crossed 00:00 UTC. Seeded jobs are stamped max(midnight + 60, now - 600 or 900) plus offsets up to 310 s, so just after local midnight they land in the future, and the server ignores jobs with created_at > now. Fails: test_http_api AdminViewsTest clients test; test_admin_ui connections view and rail order; possibly the two phone swipe tests. Fix the tests to stamp at or before now (or pin the clock); any OS can hit it.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-27T01:07:44+00:00: Fixed in tzttoq (seed_clock fits seeds between midnight and now; SeedClockTest pins 30 s after midnight; reproduced and fixed at 00:00:20 on Linux) and tluqoz (uses job_queue._local_midnight). Review ACCEPT; macOS full suite 648 OK.

## Decisions
