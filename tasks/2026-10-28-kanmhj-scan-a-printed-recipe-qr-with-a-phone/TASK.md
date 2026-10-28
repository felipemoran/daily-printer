---
id: 2026-10-28-kanmhj-scan-a-printed-recipe-qr-with-a-phone
title: Scan a printed recipe QR with a phone
status: pending
priority: 2
created_date: 2026-10-28
dependencies: []
labels: []
type: chore
parent: null
scope: null
phase: null
---

## Description

Not verified: the recipe QR (now with a 4-module quiet zone, commit omooyt) decodes with OpenCV but was never scanned with a phone camera, on screen or on paper. Once the live deploy prints to the fake printers, open a recipe PNG from ~/fake-printers/ and scan it; on a real printer, scan the paper.

## Acceptance check

<!-- AC:BEGIN -->
- [ ] A phone camera opened the deep link from a printed (or on-screen) recipe QR.
<!-- AC:END -->

## Planning

## Execution log

## Decisions
