---
id: 2026-10-12-jbm42h-simulation-tests-hang-when-web-dist-is-missing
title: Simulation tests hang when web/dist is missing
status: draft
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: fix
parent: null
scope: null
phase: null
---

## Description

Seen 2026-10-12 by the device-deps builder: the simulation tests hung for about 10 minutes in a fresh workspace before web/dist was built; with web/dist built they pass in 56 s. Not investigated. Expected: a fast, clear failure that says to run make web-build.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
