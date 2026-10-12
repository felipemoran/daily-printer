---
id: 2026-10-12-jco3n5-device-client-installs-without-playwright
title: Device client installs without Playwright
status: in-progress
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

The device client (src/print_device.py) never renders, but the device install runs uv sync on the whole project, which pulls in Playwright. Playwright has no 32-bit ARM build, so a Pi 2 or 32-bit Raspberry Pi OS cannot run a device. Operator decision 2026-10-12: devices only forward bytes to USB, so make the device install need only its own dependencies. Keep the 64-bit check for the server role.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T15:17:42+00:00: Device runs with 'uv run --script src/scripts/print_device.py': PEP 723 metadata lists aiohttp, pillow and python-escpos[usb] at the pyproject floors, and uv installs only those (confirmed: playwright, jwt, bleak not importable in the script env). tests/test_device_dependencies.py maps every load-time third-party import of the device modules to the metadata and bans playwright/jwt. Wizard device role syncs the script env (uv sync --script), skips the 32-bit refusal (now server-only), and on 32-bit ARM Linux apt-installs build-essential python3-dev libjpeg-dev zlib1g-dev because PyPI has no armv7l wheel for Pillow or PyYAML (PyYAML falls back to pure Python). systemd unit, launchd plist, make device-fake and simulate.py start devices the same way. uv (Tier 2, armv7 binaries) and python-build-standalone (armv7 gnueabihf, CPython 3.12-3.14) support armv7; no ARMv6 Python build exists. Not run on a real Pi. Full suite 583 OK; simulate --once OK on port 18787.

## Decisions
