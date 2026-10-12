---
id: 2026-10-12-skupqt-approve-a-qr-code-generator-for-templates
title: QR code generator for templates (approved if well established)
status: done
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

QRSlot needs a module matrix. Candidates to propose: 'qrcode' (npm, MIT) in the web app, or Python 'segno'/'qrcode' passing the matrix in the payload. Needs operator approval for the dependency.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:46:49+00:00: Operator (2026-10-12): adopt an industry-standard, well-established, frequently updated, widely used library; otherwise the operator picks one later.
- 2026-10-12T06:59:51+00:00: qrcode-generator 2.0.4 added in lqzyqy, wrapped in web/src/templates/qr.ts; ticket QR at 3 dots/module; QR text limited to ASCII (mrzlkn).

## Decisions

- 2026-10-12T06:47:54+00:00: decided: adopt npm qrcode-generator (MIT, 0 runtime deps, ships types, 3.6M downloads/week, 2.4k stars, v2.0.4 published 2025-08-07, repo pushed 2026-02-14), behind a small boolean[][] wrapper so it can be swapped. Runner-up uqr (5.9M/wk, 0.x). Rejected qrcode (last release 2024-08, 3 Node deps, CJS). Meets the operator's bar (well established, maintained, widely used) — easy to change
