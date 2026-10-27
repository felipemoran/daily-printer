---
id: 2026-10-27-dgz0ju-tests-seed-jobs-in-the-future-just-after-midnight
title: Tests seed jobs in the future just after midnight
status: pending
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

## Decisions
