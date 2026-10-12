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

- 2026-10-12T15:01:06+00:00: Vendored Geist and Geist Mono (geist npm 1.7.2, variable woff2, wght 100-900; 69,652 + 71,368 B) with OFL.txt and a one-line SOURCE.txt in src/static/admin/fonts/geist/. admin.css declares both with @font-face (font-display: swap) and puts them first in --sans and --mono, system stacks kept as fallbacks. /admin/{name} now matches multi-segment names but still serves only exact keys of an allowlist, which adds each fonts/*/*.woff2 as font/woff2 with no charset. The admin CSP gains font-src 'self'; without it Chromium blocks the fonts. Tests: font files served as woff2, OFL/SOURCE and traversal paths 404, and a Chromium test that both faces load with no CSP console errors (fails when font-src is removed). Full suite: 581 tests OK.

## Decisions
