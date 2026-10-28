---
id: 2026-10-28-gwm2m1-compare-linux-and-macos-renders-pixel-by-pixel
title: Compare Linux and macOS renders pixel by pixel
status: draft
priority: 3
created_date: 2026-10-28
dependencies: []
labels: []
type: chore
parent: null
scope: null
phase: null
---

## Description

Offered 2026-10-27, not started. After PR 4, Linux renders pass every test but are not pixel-identical to macOS: glyph advances differ by fractions of a pixel (5ch is 53.984 px on Linux, 54 on macOS), and CJK fallback fonts differ. Render the 16 samples on both platforms, report the pixel diff per sample, and show the ones that differ side by side. No code change.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
