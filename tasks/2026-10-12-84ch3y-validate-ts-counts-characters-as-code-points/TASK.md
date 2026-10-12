---
id: 2026-10-12-84ch3y-validate-ts-counts-characters-as-code-points
title: validate.ts counts characters as code points
status: pending
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

limitedString counts UTF-16 units, so 31 emoji fail 'at most 60 characters' while a sender counts 31. Count code points ([...s].length) and update the matching clip in src/tasks_template.py (it clips by UTF-16 units today to match). After wave 2 integration.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
