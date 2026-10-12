---
id: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
title: 'Print system: server, devices, CLI, web form, simulation — orchestrator mission log'
status: pending
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: null
scope: null
phase: null
---

## Description

Build docs/planning-print-system-architecture.md end to end. Full system simulated on one machine with fake printers. Deploy files + wizard only (Intel Mac is off; may run Linux). Admin UI last, from the operator's artifact (desktop + mobile mockups).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:20:13+00:00: Wave 1 dispatched: store, render, device, auth builders in .workspaces/ps-*, base zozvmz. Preflight PASS. Operator: senders = Access check + web form; deploy = files + wizard + local simulation; server may run Linux; rendering changes out of scope; admin UI last, mobile mockups in the artifact may be improved for touch.

## Decisions

- 2026-10-12T06:18:15+00:00: decided per-job confirmation, no per-frame acks; UI progress = frames sent — easy to change
- 2026-10-12T06:18:15+00:00: decided the admin design's push/probe/address fields map to the dial-in model: route from Cf-Ray, latency from app-level ping, address from the request — easy to change
- 2026-10-12T06:18:15+00:00: decided paper level and firmware are not tracked; client_version stands in for firmware — easy to change
- 2026-10-12T06:18:15+00:00: decided tokens in a 0600 TOML config, admin routes need the admin token (tunnel traffic looks local) — easy to change
- 2026-10-12T06:18:15+00:00: decided web sender rate limit 10 jobs per email per 10 min, body limit 10 MB, rendered PNG kept 30 days — easy to change
- 2026-10-12T06:29:12+00:00: decided reprint records the requesting admin as source and refuses a queued/sending original (409) — easy to change
- 2026-10-12T06:29:12+00:00: decided admin UI auth = Cloudflare Access + admin_emails allowlist in config; CLI keeps admin token — easy to change
