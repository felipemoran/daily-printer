---
id: 2026-10-28-ev3ztz-remove-the-mise-print-dev-workspace
title: Remove the mise-print dev workspace
status: pending
priority: 3
created_date: 2026-10-28
dependencies: []
labels: []
type: chore
parent: null
scope: null
phase: null
---

## Description

The session that built the mise-en-place prints worked in .workspaces/mise-print__daily-printer. Its PRs (4, 5) are merged. Remove it once this session ends: jworkspace-remove .workspaces/mise-print__daily-printer --yes (from the repo root). Keep .workspaces/deploy__daily-printer: the Compose deploy runs from it.

## Acceptance check

<!-- AC:BEGIN -->
- [ ] jj workspace list no longer shows mise-print__daily-printer.
- [ ] deploy__daily-printer still exists, and Compose still runs from it.
<!-- AC:END -->

## Planning

## Execution log

## Decisions
