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
- 2026-10-12T15:10:40+00:00: Rail tickets scroll on their own (operator bug: tall tickets were clipped). Each ticket's .paper-wrap is a vertical scroll container with overscroll-behavior-y: contain; the feed's fixed max-height is gone. Desktop: the rail view fills the window (body:has(#view-rail:not([hidden])) height 100dvh) and each ticket is capped at the track's height, so the sheet takes what the rail gives it. Phone: the 150 px thumbnail is now a scroll window. The -y longhand is deliberate: the shorthand blocked sideways wheel over a ticket from reaching the rail (a mutation run failed the sideways-wheel test). Polling keeps scroll because keyed() reuses nodes. Chromium tests: a tall ticket scrolls to its bottom, another ticket stays at 0, the page and rail do not move, the same node keeps its scroll across a poll that adds a job, sideways and shift-wheel move the rail, and a phone touch swipe scrolls only that ticket. Each test fails under its matching mutation.
- 2026-10-12T15:16:30+00:00: Printers and Clients tabs merged into one Connections tab (operator-approved): one link in the top nav and the phone tab bar, route #/connections with #/printers and #/clients kept as aliases, title 'Connections - Thermal', headings Printers then Clients kept, the rail footer link points to #/connections. scrollToClients and the title switch are gone; the view is view-connections. Tests cover the single tab in both navs, the three routes, the title, the heading order and the footer link. Full suite after all three commits: 585 tests OK.

## Decisions
