---
id: 2026-10-12-e0cx8m-receipt-app-wrap-long-unbroken-headings
title: 'Receipt app: wrap long unbroken headings'
status: pending
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

Requested by the print-system session: a long email (28+ chars, no break point) in .section-header / .day-header overflows the 384px band in the receipt app (web/src/App.css). Add overflow-wrap: anywhere to both; normal text renders unchanged. Regression test.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:34:56+00:00: Built ylsrzy (overflow-wrap: anywhere on .section-header/.day-header; 2 tests: overflow fixed and fails without it; normal boxes identical). Review with wave 3.
- 2026-10-12T07:46:46+00:00: Review: same bug in .receipt-header__date; one overflow-wrap on .receipt instead; byte-identical sample check requested.
- 2026-10-12T07:48:40+00:00: Fix: oxmruy (one overflow-wrap on .receipt; deprecated word-break dropped; test covers header date, section/day headers, task). Sample receipt byte-identical to base (receipt.png and print.png). Final tip oxmruy. Accepted.

## Decisions
