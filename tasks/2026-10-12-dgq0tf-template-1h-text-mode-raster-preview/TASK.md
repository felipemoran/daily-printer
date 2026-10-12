---
id: 2026-10-12-dgq0tf-template-1h-text-mode-raster-preview
title: 'Template 1h: text mode (raster preview)'
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

Implement strip 1h of Receipt Set 1 as a named template on the template infrastructure, built from design-system components.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T07:41:34+00:00: Built pykoul (build.tsx + pure textmode-lines.ts; 12 tests incl. DOM lines == buildLines; worst case 2552 dots). Review to judge: URL cut to 24 chars, 'since #N' = number-1. render_text later needs a window.templateLines(payload) export in render-main.
- 2026-10-12T07:46:46+00:00: Review: 2 should-fix (URL cut to 24 chars; 'since #N' computed), limits vs printed cells (decided: truncate with ~, documented), nits (emoji fold, charset test, NIGHTLY). Fix round sent.
- 2026-10-12T07:48:01+00:00: Fix: wzzqpu (URL wraps in full; optional since; optional name uppercased; /gu fold; output charset test; 16 tests). Re-review sent.
- 2026-10-12T07:48:46+00:00: Re-review: wzzqpu correct; nit (cap number/since at 9,999,999) sent.
- 2026-10-12T07:49:37+00:00: Nit: sxyzoo (number, since and commits capped at 9,999,999; longest title and commits line uncut). Final tip sxyzoo. Accepted.

## Decisions
