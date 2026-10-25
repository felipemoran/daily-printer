---
id: 2026-10-12-c8os24-template-tasks-from-design-system-taskstemplate
title: 'Template 1b: tasks (plus daily data through it, for comparison)'
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

Port design-system/components/TasksTemplate/preview.html into a named template with typed data, following the infrastructure's template convention. Sample payload = the preview's own content. Render must match the preview's layout.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:46:49+00:00: Operator (2026-10-12): keep today's daily receipt unchanged; also make today's Todoist data printable through the 1b template so both can be compared on paper.
- 2026-10-12T07:03:38+00:00: Built xpnnyl; in wave-1 review + verification (throwaway merge qpwvkput).
- 2026-10-12T07:07:36+00:00: Review: 4 should-fix (UTF-16 vs code-point clip fails renders, >30 tasks fails, unbroken URL clipped, duplicated render/print helper), 5 nits. Fix round 1 sent.
- 2026-10-12T07:10:41+00:00: Fix round 1: mxuyxx (UTF-16 clip, trim 30 + more, wrap anywhere, shared render_and_print, TaskSections mapping with P1-P3, OVERDUE ND meta; 7 tests). Re-review sent.
- 2026-10-12T07:11:42+00:00: Re-review: accepted; 2 nits sent (skip dist payload write in --template, public strip_markdown_links).
- 2026-10-12T07:12:14+00:00: Nits: zpunmn (--template skips dist payload write; public strip_markdown_links). Final tip zpunmn.

## Decisions
