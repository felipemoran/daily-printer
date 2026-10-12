---
id: 2026-10-12-e4d0a7-admin-interface-uses-vendored-geist-fonts
title: Admin interface uses vendored Geist fonts
status: in-progress
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

The admin mockup specifies Geist and Geist Mono; the admin interface (src/static/admin) uses system fonts. Operator decision 2026-10-12: vendor the fonts into the repo and use them. Self-host, so the admin CSP stays same-origin. Tickets keep their own vendored fonts in web/public/fonts. Also: make simulate prints the /admin URL.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
