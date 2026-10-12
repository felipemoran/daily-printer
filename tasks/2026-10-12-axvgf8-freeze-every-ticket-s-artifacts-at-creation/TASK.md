---
id: 2026-10-12-axvgf8-freeze-every-ticket-s-artifacts-at-creation
title: Freeze every ticket's artifacts at creation
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

Operator request 2026-10-12: persist each ticket as it was created, so a later template, font or code change never alters past tickets, and no re-render is needed. Keep the input data, the rendered page, the raw screenshot and the final printed image, for regression checks, before/after comparison of redesigns, and data mining. Operator decisions: keep them forever (no automatic prune); one folder per job on disk, with SQLite as the index.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
