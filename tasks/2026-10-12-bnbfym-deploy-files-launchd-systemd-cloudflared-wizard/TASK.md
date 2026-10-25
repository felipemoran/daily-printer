---
id: 2026-10-12-bnbfym-deploy-files-launchd-systemd-cloudflared-wizard
title: 'Deploy files: launchd, systemd, cloudflared, wizard'
status: done
priority: 2
created_date: 2026-10-12
dependencies:
- 2026-10-12-mwo0xv-server-device-hub-http-api-entry-point
labels: []
type: null
parent: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
scope: null
phase: null
---

## Description

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions

- 2026-10-12T07:39:16+00:00: decided to apply the last two wizard fixes (libusb gate, journal --since timestamp) without a third review round: two rounds done, findings converging, fixes are one-liners; the wave gate runs bash -n/shellcheck/tests — easy to change
