---
id: 2026-10-12-db5wwf-template-render-infrastructure-payload-render-page
title: 'Template infrastructure + template 1c: ticket update'
status: done
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

Named templates with typed data. Payload {template, schemaVersion, data}. One Vite page renders a payload into the 384-dot #receipt; a Python render_job(payload, page) returns the 1-bit image through the paper-tested print profile; print_template.py payload.json [--no-print] prints locally. Ticket is the first template (port of design-system TicketTemplate with its sample content as data). Interface details are negotiated with the print-system session.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:51:47+00:00: Built qsqvkr. Verifier: gates green (73 tests). Review: 1 blocker (effect-time throw renders blank as success), 4 should-fix, 3 nits. Fix round 1 sent to the same builder with the QR slot (qrcode-generator 2.0.4).
- 2026-10-12T06:59:51+00:00: Done: qsqvkr (infrastructure + 1c ticket), lqzyqy (review fixes + QR slot), mrzlkn (ASCII-only QR text). Review: 1 blocker + 4 should-fix + 3 nits fixed over 2 rounds; final round no findings. Verifier: 77 tests green on lqzyqy; daily receipt path still renders.

## Decisions
