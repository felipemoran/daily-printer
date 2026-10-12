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
- [x] `src/scripts/print_device.py` declares its dependencies in PEP 723 metadata (aiohttp, pillow, python-escpos[usb], pyproject floors); `src/scripts/print_device.py.lock` pins them.
- [x] `uv run --script` and `uv sync --script` install only those and read the lock; playwright and jwt are not importable there (checked locally).
- [x] `tests/test_device_dependencies.py` fails on an undeclared device import, lazy ones included (bleak allowed in printer.py only), on any playwright or jwt import, and on a stale lock.
- [x] `deploy/wizard.sh device` syncs only the script environment, has no 32-bit refusal, and on 32-bit ARM Linux runs apt-get update and installs the Pillow build tools; `deploy/wizard.sh server` keeps the refusal.
- [x] The systemd unit, launchd plist, `make device-fake` and `simulate.py` start the device with `uv run --script`.
- [x] Docs state the device platforms, the lock, the ARMv6 exclusion and the sources.
- [x] Full suite passes; `simulate.py --once` prints both jobs.
- [ ] A device runs on a real 32-bit Raspberry Pi (Pi 2 or later): wizard, Pillow build, service, one printed job.
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T15:17:42+00:00: Device runs with 'uv run --script src/scripts/print_device.py': PEP 723 metadata lists aiohttp, pillow and python-escpos[usb] at the pyproject floors, and uv installs only those (confirmed: playwright, jwt, bleak not importable in the script env). tests/test_device_dependencies.py maps every load-time third-party import of the device modules to the metadata and bans playwright/jwt. Wizard device role syncs the script env (uv sync --script), skips the 32-bit refusal (now server-only), and on 32-bit ARM Linux apt-installs build-essential python3-dev libjpeg-dev zlib1g-dev because PyPI has no armv7l wheel for Pillow or PyYAML (PyYAML falls back to pure Python). systemd unit, launchd plist, make device-fake and simulate.py start devices the same way. uv (Tier 2, armv7 binaries) and python-build-standalone (armv7 gnueabihf, CPython 3.12-3.14) support armv7; no ARMv6 Python build exists. Not run on a real Pi. Full suite 583 OK; simulate --once OK on port 18787.
- 2026-10-12T15:39:01+00:00: Review round: the guard now checks every import, lazy ones included (bleak allowed in printer.py only; a lazy 'import dotenv' in src/print_device.py now fails it). Added src/scripts/print_device.py.lock; uv run/sync --script read it (proved with a scratch script locked to an old idna) and a test runs 'uv lock --script --check' (skipped without uv). Wizard runs apt-get update before both apt installs. Docs: ARMv6 not supported (.python-version pins 3.12, no ARMv6 build); 'should run, not yet tested on a Pi'; old services without --script move to the script env at their next restart and need the network once. Device+deploy+dependency tests 56 OK; full suite 584 OK; simulate --once OK on port 18788. Still not run on a real Pi.
- 2026-10-12T15:46:19+00:00: Round 2 review: wizard syncs the device with 'uv sync --locked --script' (service keeps plain 'uv run --script' to avoid a restart loop on a stale lock). New test refuses a module-level bleak import in printer.py; a load-time 'from bleak import BleakScanner' mutation fails it. UV lookup is shutil.which($UV or 'uv'), so a missing UV path skips the lock test. Device, deploy and dependency tests: 57 OK.

## Decisions
