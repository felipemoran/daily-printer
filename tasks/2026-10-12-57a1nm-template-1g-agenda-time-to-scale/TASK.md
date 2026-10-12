---
id: 2026-10-12-57a1nm-template-1g-agenda-time-to-scale
title: 'Template 1g: agenda (time to scale)'
status: done
priority: 2
created_date: 2026-10-12
dependencies:
- 2026-10-12-db5wwf-template-render-infrastructure-payload-render-page
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

Implement strip 1g of Receipt Set 1 as a named template on the template infrastructure, built from design-system components.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:42:41+00:00: Built tnkkqz (agenda.tsx, sample, 13 tests; worst case 2675 dots). Rules: out-of-window refused; ≤2 overlapping lanes; per-edge rounding; labels by a width model, else an UNLABELLED list. In review.
- 2026-10-12T07:47:44+00:00: Review: 🔴 width model under-counts emoji (1.25 em) and CJK, so valid agendas are refused by the fit guard (reproduced). Fix sent: measure labels after fonts load (focus.tsx pattern); tests at the exact limit; drop FOCUS prefix in boxes.
- 2026-10-12T07:49:58+00:00: Fix: tnxyrq (labels measured after fonts load; FOCUS prefix dropped in boxes; limit-search tests for CJK and emoji; 15 tests). Re-review sent.
- 2026-10-12T08:03:02+00:00: Re-review: approved (1280-case sweep, 0 refusals). Nit (cached rejected font promise; font failure surfaces as TemplateError) folded into the render_text task: keep the rejection cached (as 1n) and classify font-load failures as server faults. Final tip tnxyrq.

## Decisions
