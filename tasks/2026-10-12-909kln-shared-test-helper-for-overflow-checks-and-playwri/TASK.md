---
id: 2026-10-12-909kln-shared-test-helper-for-overflow-checks-and-playwri
title: Shared test helper for overflow checks and Playwright setup
status: draft
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

About 12 test modules copy the same overflow-check JS and Playwright page setup; one helper would delete that.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T03:14:34+00:00: 2026-10-26: tests/test_template_recipe.py and tests/test_template_shopping_list.py add two more copies of _OVERFLOW_JS, _TEXTS_JS, assert_in_order and the browser setUp (review of change ywwpzu).

## Decisions
