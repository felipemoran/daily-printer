---
id: 2026-10-12-8e3zo3-blank-visible-strings-in-report-review-queue-tasks
title: Blank visible strings in report, review-queue, tasks
status: in-progress
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: implementing
---

## Description

Found by the docs pass: report (range, title, KPI label), review-queue (title, area) and tasks still accept blank visible strings (built before the shared nonBlank/text() helpers). A blank title prints an empty line and reports success. Apply text(max) to every required visible string; refusal tests; then update the docs rule to say every template does it. Run after the test-build cleanup (shared test files).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
