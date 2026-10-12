---
id: 2026-10-12-db5wwf-template-render-infrastructure-payload-render-page
title: 'Template render infrastructure: payload, render page, render_job, CLI'
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

Named templates with typed data. Payload {template, schemaVersion, data}. One Vite page renders a payload into the 384-dot #receipt; a Python render_job(payload, page) returns the 1-bit image through the paper-tested print profile; print_template.py payload.json [--no-print] prints locally. Ticket is the first template (port of design-system TicketTemplate with its sample content as data). Interface details are negotiated with the print-system session.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
