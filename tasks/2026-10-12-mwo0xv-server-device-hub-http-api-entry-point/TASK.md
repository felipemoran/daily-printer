---
id: 2026-10-12-mwo0xv-server-device-hub-http-api-entry-point
title: 'Server: device hub, HTTP API, entry point'
status: in-progress
priority: 2
created_date: 2026-10-12
dependencies:
- 2026-10-12-3v6m27-store-job-metadata-events-printer-state-stats-repr
- 2026-10-12-0xf0fj-render-job-content-to-bitmap-png-and-esc-pos
- 2026-10-12-q5vtnu-device-client-websocket-loop-usb-and-fake-sinks
- 2026-10-12-w5ceqk-config-and-cloudflare-access-token-check
labels: []
type: null
parent: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
scope: null
phase: implementing
---

## Description

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:29:12+00:00: From store review: at startup the hub must clear connected_since/address in printer state (they survive restarts). Render calls must be bounded: no sender input may hang a worker or escape as a non-RenderError (class found in render review).

## Decisions
