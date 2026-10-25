---
id: 2026-10-12-84ch3y-validate-ts-counts-characters-as-code-points
title: validate.ts counts characters as code points
status: done
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

limitedString counts UTF-16 units, so 31 emoji fail 'at most 60 characters' while a sender counts 31. Count code points ([...s].length) and update the matching clip in src/tasks_template.py (it clips by UTF-16 units today to match). After wave 2 integration.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:20:39+00:00: Also: nonBlank must treat zero-width characters (U+200B-U+200D, U+2060, U+FEFF) as blank; dedupe the integer()/text() helpers duplicated in briefing.tsx and focus.tsx into validate.ts.
- 2026-10-12T07:42:04+00:00: Also add integer(min, max) and a min-length option for array() to validate.ts; replace the hand-written copies (briefing.integer, tasks, report, habits, sprint.wholeNumber/atLeastOne, leaderboard people, uptime/habits min checks).
- 2026-10-12T08:10:48+00:00: Built tkunlq (integer/array min/text helpers; 17 copies removed; code-point limits; zero-width blank; faults.ts ServerFault in focus/agenda; 108 template tests; 14 samples byte-identical). In review.
- 2026-10-12T08:13:14+00:00: Reviewed: approved. Integrated in merge zspqqk. Nits (ZWJ test, focus message wording, inline whole) go to the render_text fix round.

## Decisions
