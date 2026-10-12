---
id: 2026-10-12-jco3n5-device-client-installs-without-playwright
title: Device client installs without Playwright
status: pending
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: null
---

## Description

The device client (src/print_device.py) never renders, but the device install runs uv sync on the whole project, which pulls in Playwright. Playwright has no 32-bit ARM build, so a Pi 2 or 32-bit Raspberry Pi OS cannot run a device. Operator decision 2026-10-12: devices only forward bytes to USB, so make the device install need only its own dependencies. Keep the 64-bit check for the server role.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
