---
id: 2026-10-12-bh037i-template-reminder-from-design-system-remindertempl
title: 'Template 1n: focus ticket'
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

Port design-system/components/ReminderTemplate/preview.html into a named template with typed data, following the infrastructure's template convention. Sample payload = the preview's own content. Render must match the preview's layout.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:12:11+00:00: Built sytyor (focus.tsx, sample, 7 tests). Title takes the largest of display-lg/md/sm at which its longest word fits; suspends on fonts.load via use(); measures in render.

## Decisions
