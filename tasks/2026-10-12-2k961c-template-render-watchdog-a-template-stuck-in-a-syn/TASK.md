---
id: 2026-10-12-2k961c-template-render-watchdog-a-template-stuck-in-a-syn
title: 'Template render watchdog: a template stuck in a sync busy loop could freeze page.evaluate past the 3 s in-page timeout'
status: draft
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
scope: null
phase: null
---

## Description

Reported by the design-system session; no current template can loop. Option: close the page/browser from a worker-level watchdog after ~10 s. Deferred: needs a thread-safe way to kill a sync Playwright browser.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:56:35+00:00: Wave 4 review: the measure/fit/profile page.evaluate calls have no timeout for both receipt and template kinds; nothing outside the render enforces a time limit. A worker-level watchdog would cover both. No sender input found that hangs today.

## Decisions
