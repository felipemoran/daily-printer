---
id: 2026-10-12-o7efgw-render-time-fit-guard-refuse-renders-whose-text-ov
title: 'Render-time fit guard: refuse renders whose text overflows its box'
status: in-progress
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: implementing
---

## Description

Structural fix for the bug class found in wave-1 reviews: text inside a fixed-width design-system cell (overflow:hidden / nowrap) is silently clipped and prints a wrong value while the render succeeds. After the render settles, render_template must check every element under #receipt and raise TemplateError naming the offending text when any element's content is wider than its box (scrollWidth > clientWidth beyond a 1px tolerance) or extends past the receipt's printable edge. Applies to every template, present and future.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:16:02+00:00: Built vzoxqn (fit check in render_template: paper edge, horizontal/vertical clip, text spill; 28 tests). Review + verification on wave 1 sent.
- 2026-10-12T07:19:55+00:00: Extra commit requested: refuse renders whose layout changed between measurement and capture (structural guard for the 1n stale-layout class).
- 2026-10-12T07:20:58+00:00: Review: 2 should-fix (lineHeight/2 vertical tolerance hides partial clips; text spill checked on one axis), 2 nits. Sent as a further commit after the capture-length guard.
- 2026-10-12T07:24:29+00:00: pmtrqn (capture-length guard: measure, compare image, re-measure after screenshot) and llroup (review findings: 3-dot vertical tolerance, paper-axis text check, TextMode tests, zero-size clip boxes); 24 tests. Re-review sent.
- 2026-10-12T07:25:16+00:00: Re-review round 1: llroup confirmed; pmtrqn refuses fractional heights < .5 (offset* rounds, capture rounds up). Fix sent.
- 2026-10-12T07:26:22+00:00: yrkxum: length measured as ceil(getBoundingClientRect) everywhere (25 tests). Viewport-sizing commit requested next.
- 2026-10-12T07:29:39+00:00: rqmkok: viewport sized to the receipt before capture; fallback face now identical at resolve and capture on 3 fresh pages (Times, 918 dots); 26 tests. Final re-review sent.

## Decisions
