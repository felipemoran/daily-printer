---
id: 2026-10-12-iyhvoa-test-suite-build-the-web-app-once
title: 'Test suite: build the web app once'
status: pending
priority: 3
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

Several test modules (test_ticket_templates, test_design_system, test_template_tasks, test_template_incident, ...) each run npm run build or their own setup. Build once per test run (a shared helper or module-level fixture) and move the ticket blank-field tests from test_template_incident.py into test_ticket_templates.py. Do after the template waves, when no builder owns the shared test files.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
