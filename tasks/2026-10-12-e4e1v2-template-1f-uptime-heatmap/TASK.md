---
id: 2026-10-12-e4e1v2-template-1f-uptime-heatmap
title: 'Template 1f: uptime heatmap'
status: in-progress
priority: 2
created_date: 2026-10-12
dependencies:
- 2026-10-12-db5wwf-template-render-infrastructure-payload-render-page
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: implementing
---

## Description

Implement strip 1f of Receipt Set 1 as a named template on the template infrastructure, built from design-system components.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:09:30+00:00: Built zrzolw (uptime.tsx, sample, 4 tests). Label column 51px so 51 + 24x11 + 23x3 = 384 exactly; ticks placed by the template on whole-pixel cell starts.
- 2026-10-12T07:17:04+00:00: Review: 2 should-fix (blank inputs print; ﷽ worst case), DS legend fractional, 2 nits. Fix round 1 sent (nonBlank, floor percent); wide-glyph inputs left to the height limit and fit guard.
- 2026-10-12T07:19:22+00:00: Fix round 1: commit 86bf95 (change lznzzs; nonBlank fields, uptime truncated not rounded; 5 tests). Change id is divergent with an empty duplicate 1dba31 — abandoning it was refused by the permission system; left for the operator. Address the fix by commit id 86bf95.
- 2026-10-12T07:20:39+00:00: Re-review: no new findings. Final tip: commit 86bf95. Accepted.

## Decisions
