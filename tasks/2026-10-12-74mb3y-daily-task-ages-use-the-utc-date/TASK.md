---
id: 2026-10-12-74mb3y-daily-task-ages-use-the-utc-date
title: Daily task ages use the UTC date
status: draft
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

Pre-existing (found reviewing 1b): task_formatter._today() takes the UTC date for 'N days ago' while the masthead uses local time; a run after 21:00 at UTC-03:00 is off by one day. The 07:30 run is consistent.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
