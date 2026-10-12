---
id: 2026-10-12-8vbqh7-template-report-from-design-system-reporttemplate
title: 'Template 1e: weekly report'
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

Port design-system/components/ReportTemplate/preview.html into a named template with typed data, following the infrastructure's template convention. Sample payload = the preview's own content. Render must match the preview's layout.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:03:38+00:00: Built qktzpq; in wave-1 review + verification (throwaway merge qpwvkput).
- 2026-10-12T07:06:58+00:00: Review: 2 blockers (values >= 10,000 silently clipped in BarList/Columns cells — wrong numbers print), 1 should-fix (unbounded labels), 3 nits. Fix round 1 sent.
- 2026-10-12T07:10:12+00:00: Fix round 1: ztmwuo (fit formatter, label bounds, odd KPI counts 1-up, 32px section margins; 8 tests). Re-review sent. Open: free-text KPI value can overflow a tile — addressed by the render-time fit guard task.
- 2026-10-12T07:11:28+00:00: Re-review: 2 nits; -0 normalization sent; tiny fractions printing 0 accepted.
- 2026-10-12T07:12:11+00:00: Fix: xxokyz (-0 → 0; 9 tests). Accepted.

## Decisions
