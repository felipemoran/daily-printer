---
id: 2026-10-12-vw4bl6-template-images-await-decode-and-snap-to-whole-pix
title: 'Template images: await decode and snap to whole pixels'
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

From review of the infrastructure: render-main does not await <img> decode and does not apply page_print's whole-pixel snap. T.Image changes height onLoad, after the too-tall check, so a future image template (meme, recipe, photo) would be measured wrong and its bitmap resampled. Fix when the first image template lands.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:25:16+00:00: Now required, not optional: the capture-length guard refuses a T.Image without height that loads after fonts.ready. Image templates must pass height or the render must await img.decode().

## Decisions
