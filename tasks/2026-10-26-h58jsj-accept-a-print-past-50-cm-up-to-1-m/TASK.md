---
id: 2026-10-26-h58jsj-accept-a-print-past-50-cm-up-to-1-m
title: Accept a print past 50 cm, up to 1 m
status: done
priority: 1
created_date: 2026-10-26
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: null
---

## Description

Operator decision 2026-10-26: a template job longer than 50 cm is refused with a reply the sender can act on: a stable code and the measured length. The sender may resend the same job with an accept flag; then any template job prints up to a hard cap of 1 m, and past 1 m it is refused outright. First sender: the mise-en-place print button (tasks 1z19qx, vsz7c3; mise-en-place tbdq8p, 33hqgk).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T03:53:01+00:00: Built in unxqst (h58jsj), zoryqy (bjycpj), tlovqq (g3t12q), with review fixes in ypuqrk. Gatekeeper round 2 ACCEPT: web lint, web build, full serial suite 690 tests OK including test_print_server_e2e.
- 2026-10-27T01:00:01+00:00: Local end-to-end run 2026-10-26: real mise-en-place site and catalogue, this server with the redesigned templates, a stand-in for Access, real Chromium CORS, fake printer. Week list: GET /api/me 200, OPTIONS 204, POST 201, printed 24.8 cm. Panqueca (book recipe, 4 components, 14 steps): 201, 46.7 cm. Madalena at 40 portions: 201, 47.1 cm. Stored payloads byte-identical to the page's. QR decodes to the deep link after the quiet-zone fix (omooyt). Not exercised end to end: the accept-long confirm (no real print passes 50 cm); covered by test_cross_origin_browser and the site tests. mise-en-place side merged as PR 17 (4048b3ba).

## Decisions
