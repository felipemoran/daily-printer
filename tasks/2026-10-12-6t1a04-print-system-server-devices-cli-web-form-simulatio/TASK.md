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
- 2026-10-12T06:42:55+00:00: Wave 1 closed: store kvpurollmxxy, render uwllyzrzotky, config/Access npxynsqkyvzl, device xxwwynzvkqoq, linearized after mqtypz. Each reviewed (review skill, reviewer != builder), all findings fixed; gate PASS: 195 tests twice, compileall, imports, clean tree.
- 2026-10-12T07:17:53+00:00: Wave 2 closed: server sxotkrlvyumy + render pixel cap rqvtxonvlkws. Two reviewers (hub reliability, HTTP security); CSRF blocker fixed and re-reviewed; gate PASS: 270 tests twice, real server start/API/SIGTERM.
- 2026-10-12T07:46:26+00:00: Wave 3 closed: device fix ostuxq, CLI wxqkqu, web form qvolrx, simulation usqmqu, deploy kzzrqm. All reviewed (deploy two rounds + final nits), gate PASS: 353 tests twice, real server, simulate --once, deploy file checks.

## Decisions

- 2026-10-12T06:18:15+00:00: decided per-job confirmation, no per-frame acks; UI progress = frames sent — easy to change
- 2026-10-12T06:18:15+00:00: decided the admin design's push/probe/address fields map to the dial-in model: route from Cf-Ray, latency from app-level ping, address from the request — easy to change
- 2026-10-12T06:18:15+00:00: decided paper level and firmware are not tracked; client_version stands in for firmware — easy to change
- 2026-10-12T06:18:15+00:00: decided tokens in a 0600 TOML config, admin routes need the admin token (tunnel traffic looks local) — easy to change
- 2026-10-12T06:18:15+00:00: decided web sender rate limit 10 jobs per email per 10 min, body limit 10 MB, rendered PNG kept 30 days — easy to change
- 2026-10-12T06:29:12+00:00: decided reprint records the requesting admin as source and refuses a queued/sending original (409) — easy to change
- 2026-10-12T06:29:12+00:00: decided admin UI auth = Cloudflare Access + admin_emails allowlist in config; CLI keeps admin token — easy to change
- 2026-10-12T07:00:40+00:00: decided after a device error or reply timeout, pause delivery to that printer 60 s (job stays queued, expiry applies) so out-of-paper does not burn 3 attempts in seconds — easy to change
- 2026-10-12T07:00:40+00:00: decided server closes a device connection silent for 60 s; protocol violations release the job and close the connection; title <= 200 chars; expires_in <= 7 days — easy to change
- 2026-10-12T07:28:56+00:00: decided web form: Title only in Message mode (photos print no title); sender email shown via a wrapping block, not a section_header (no edits to web/src CSS, owned by the design-system session); CSP on GET / — easy to change
