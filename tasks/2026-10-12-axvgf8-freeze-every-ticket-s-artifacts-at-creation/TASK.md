---
id: 2026-10-12-axvgf8-freeze-every-ticket-s-artifacts-at-creation
title: Freeze every ticket's artifacts at creation
status: in-progress
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

Operator request 2026-10-12: persist each ticket as it was created, so a later template, font or code change never alters past tickets, and no re-render is needed. Keep the input data, the rendered page, the raw screenshot and the final printed image, for regression checks, before/after comparison of redesigns, and data mining. Operator decisions: keep them forever (no automatic prune); one folder per job on disk, with SQLite as the index.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T15:29:50+00:00: Built in workspace artifacts__daily-printer, not pushed. Each job is frozen at intake in <database dir>/artifacts/<job id>/: payload.json, source.<ext> (image), page.mhtml, screenshot.png, print.png, job.escpos, meta.json (kind, template, created_at, width, height, render_ms, web_dist_sha256, reprint_of). The folder is staged as .tmp-*, then renamed to the job id inside the insert transaction; a failed write or rename gives 500 with no folder and no job; .tmp-* folders are swept at server start; a crash between rename and commit leaves an orphan folder no job names. Chromium 145 Page.captureSnapshot drops web fonts, so the server adds data:-URL copies of each fetched @font-face rule before the snapshot; the receipt app uses system fonts (Tahoma, Verdana), so its MHTML has none. The PNG BLOB and its 30-day prune are gone; the image route serves print.png. Reprint copies the folder (hard links), sends the source's job.escpos, keeps the kind (text stays text), and records reprint_of; a job without a folder gets 409. printctl show prints the folder (field artifacts on GET /api/jobs/{id}). Disk: 210-280 KB per template ticket, mostly fonts in page.mhtml. Full suite: 588 tests OK; simulate --once OK.

## Decisions
