---
id: 2026-10-28-37j020-fake-printer-flag-in-the-device-launchd-template
title: Fake-printer flag in the device launchd template
status: draft
priority: 3
created_date: 2026-10-28
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: null
---

## Description

The 2026-10-27 local deploy added '--fake <dir>' by hand to the two rendered LaunchAgents (com.daily-printer.device.cozinha/.escritorio), because deploy/launchd/com.daily-printer.device.plist has no slot for it. Only worth doing if fake printers become a supported deploy mode.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
