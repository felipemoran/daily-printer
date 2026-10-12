---
id: 2026-10-12-jjnbce-smaller-payload-limit-for-web-senders-a-4-mb-recei
title: Smaller payload limit for web senders (a 4 MB receipt payload holds a render worker ~10 s)
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

Render review measured: Chromium's first layout of an 80k-block receipt takes ~10 s; no in-browser probe can reject it faster. Web senders are rate-limited (10 per 10 min per email), so this is a follow-up, not a blocker. Option: lower body limit for ingress=web (e.g. 1 MB) or a max block count at intake. Operator decision: it limits what senders can submit.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
