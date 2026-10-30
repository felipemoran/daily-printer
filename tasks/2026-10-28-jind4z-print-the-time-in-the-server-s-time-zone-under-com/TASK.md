---
id: 2026-10-28-jind4z-print-the-time-in-the-server-s-time-zone-under-com
title: Print the time in the server's time zone under Compose
status: operator
priority: 1
created_date: 2026-10-28
dependencies: []
labels: []
type: fix
parent: null
scope: null
phase: null
---

## Description

Found 2026-10-27 in the local Compose deploy: the container has no TZ, so the recipe and shopping-list footer ('impresso em …') prints UTC (00:05 while the Mac showed 22:05). Proposed fix: compose.yaml passes TZ from .env into the server container, set to the host's zone. Waiting on the operator to approve the repo change and its merge.

## Acceptance check

<!-- AC:BEGIN -->
- [ ] The server container's footer prints the host's local time, checked on a real print.
- [ ] The operator approved the compose.yaml change, or decided to keep UTC.
<!-- AC:END -->

## Planning

## Execution log

## Decisions
