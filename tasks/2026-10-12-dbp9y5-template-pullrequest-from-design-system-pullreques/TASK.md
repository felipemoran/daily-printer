---
id: 2026-10-12-dbp9y5-template-pullrequest-from-design-system-pullreques
title: 'Template 1i: review queue'
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

Port design-system/components/PullRequestTemplate/preview.html into a named template with typed data, following the infrastructure's template convention. Sample payload = the preview's own content. Render must match the preview's layout.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:02:35+00:00: Built vyqpou (review-queue.tsx, sample, 5 tests). Ages are whole days, so sub-day PRs show 0D where strip 1i shows hours.
- 2026-10-12T07:03:38+00:00: Built vyqpou; in wave-1 review + verification (throwaway merge qpwvkput).
- 2026-10-12T07:06:58+00:00: Review: 1 should-fix (cap 10 too low), 2 nits (sort oldest first, safe-integer bound). Fix round 1 sent.
- 2026-10-12T07:08:04+00:00: Fix round 1: suwuvo (cap 25, oldest-first sort, integer bounds, clipping guard test; 7 tests). Awaiting re-review.
- 2026-10-12T07:11:28+00:00: Re-review: cap 25 lets valid lists exceed 4000 dots; lowering to 20 with a worst-case height test. Constant-only change, accepted without another review round.
- 2026-10-12T07:12:55+00:00: Fix: wxspro (cap 20; title ≤64, area ≤10, diffs ≤999,999 so the 20-row worst case is 3714 dots; 8 tests). Final tip wxspro. Accepted.

## Decisions
