---
id: 2026-10-12-k00yec-design-system-fixes-to-make-in-claude-design
title: Design-system fixes to make in Claude Design
status: draft
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

Issues found while building templates that belong in the Claude Design source (design-system/ is a verbatim mirror, never edited here): (1) Tag width comes from glyph widths plus letter-spacing, so its box is fractional (e.g. 108.81px; right-aligned left edge at x=275.19) — violates the whole-pixel rule for a reversed block. Fix: round the tag's width, or give it a whole-pixel min-width/padding so the box lands on whole dots.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:03:33+00:00: (2) BarList previous-period bar (.rp-bar-b) is border-box with a 2px border, so value 0 prints as a 4px outlined stub and any bar under 4px prints at 4px (found building 1e).
- 2026-10-12T07:09:30+00:00: (3) CellGrid ticks use justify-content: space-between, so tick text lands on fractional x and drifts from the hour columns (found building 1f; the template places its own ticks).

## Decisions
