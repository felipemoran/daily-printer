---
id: 2026-10-12-bh037i-template-reminder-from-design-system-remindertempl
title: 'Template 1n: focus ticket'
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

Implement the `focus` template from Receipt Set 1 strip 1n, as a named template with typed data that follows the template convention. Its sample payload is `samples/templates/focus.json`. (The task first planned a port of the design system's ReminderTemplate; Receipt Set 1 replaced that plan.)

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:12:11+00:00: Built sytyor (focus.tsx, sample, 7 tests). Title takes the largest of display-lg/md/sm at which its longest word fits; suspends on fonts.load via use(); measures in render.
- 2026-10-12T07:19:55+00:00: Review: 1 should-fix reproduced (fresh page + Cyrillic: render resolves on a stale layout; PNG ends in a grey band; success reported), 2 nits. Fix round 1 sent (root cause + test).
- 2026-10-12T07:26:12+00:00: Fix round 1: nxlxuw. Root cause: system fallback face for glyphs missing from bundled fonts changes (Times-Bold -> Menlo-Bold) when the screenshot resizes the viewport. Builder's fix refuses non-Latin text in focus — held pending an infra fix (viewport sized before capture); then re-test with the refusal off.
- 2026-10-12T07:32:32+00:00: lkrslv: non-Latin refusal removed after the viewport fix; fresh-page Cyrillic/CJK/Latin-1 renders 36/36 pass. Chain sytyor-nxlxuw-lkrslv on otvylkrs. Re-review sent (with 1l wvkyvv).
- 2026-10-12T07:33:39+00:00: Re-review: grey band fixed (fresh Cyrillic 384x916, heights equal); 2 nits sent (header row nowrap, keep rejected font promise cached).
- 2026-10-12T07:35:03+00:00: Nits: uptqzv (header label nowrap, id wraps in its span; rejected font promise stays cached). Final tip uptqzv. Accepted; integrate with wave 3.

## Decisions
