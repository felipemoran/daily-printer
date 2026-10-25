---
id: 2026-10-12-v9hd3o-print-the-thermal-test-strips-and-settle-verify-md
title: Print the Thermal test strips and settle verify.md
status: draft
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: null
scope: null
phase: null
---

## Description

The open paper checks in design-system/verify.md need prints of the Test strips (TestType, TestStrokes, TestTones, TestSolids, TestQR). Postponed by the operator on 2026-10-12. Print one with: cd web && npm run build, then uv run src/scripts/page_print.py --page 'web/dist/preview.html?c=TestTones'. Each strip's README.md in design-system/ says what to look for. Settle the results in Claude Design, then make design-sync.

## Acceptance check

Each open check in design-system/verify.md has a recorded result in Claude Design, and the synced design-system/ reflects it.

## Planning

## Execution log

## Decisions
