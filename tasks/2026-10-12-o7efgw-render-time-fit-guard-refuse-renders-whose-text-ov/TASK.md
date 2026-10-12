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

## Decisions
