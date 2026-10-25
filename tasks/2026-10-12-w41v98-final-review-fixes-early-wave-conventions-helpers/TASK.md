---
id: 2026-10-12-w41v98-final-review-fixes-early-wave-conventions-helpers
title: 'Final review fixes: early-wave conventions, helpers, test hygiene'
status: done
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

From the final cross-cutting review of mvmknm: ticket/report/incident/qr.ts lack text(max) caps and nonBlank (ticket kind/time/comment.author, empty qr.text encodes nothing, incident summary whitespace); worst-case height tests for ticket and report; shared range(min,max) and oneOf in validate.ts replacing 4+2 copies and agenda's fail; one facesLoaded helper for focus/agenda; leaderboard false -0 comment; dead exports in textmode-lines.ts; stale 'No landscape template yet' test comment; tests/web_build.py: RuntimeError instead of SkipTest when node_modules is missing, and reuse src/web_build.build_web with functools.cache so build errors are visible; docs: max_height_dots in the API table, and 'every template refuses blank visible strings'.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T08:45:30+00:00: ssvrkq: all 8 findings fixed (210 tests, 0 skips; samples byte-identical). Build seconds now inclusive 0..359999. New leftover: tasks worst case 10831 dots (valid payload refused) — follow-up commit to set caps so it fits, mapping trims to the new cap.
- 2026-10-12T08:48:05+00:00: oqtpyu: tasks caps 8 tasks / title 80 / meta 40 (worst case W 2427, CJK 3167, emoji 3935 dots); mapping trims to 8 with +N MORE. Re-review sent.
- 2026-10-12T08:49:13+00:00: Re-review: approved; all 14 samples byte-identical (independent build). Nits sent (facesLoaded Map by key; duplicate node_modules check). The 8-task cap needs the operator's ACK.
- 2026-10-12T08:50:11+00:00: qrwtro (facesLoaded Map by key). Integrated in final merge vntkpt.

## Decisions
