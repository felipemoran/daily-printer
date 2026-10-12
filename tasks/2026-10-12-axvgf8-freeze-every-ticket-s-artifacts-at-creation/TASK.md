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
- [x] Every job gets `<database dir>/artifacts/<job id>/` at intake, with the files of its kind; `print.png` and `job.escpos` equal what was queued and sent (`test_each_kind_keeps_its_files_and_the_bytes_it_queued_and_sent`).
- [x] `payload.json` keeps the input values exactly, as compact JSON no larger than the request (`test_payload_json_round_trips_the_input`, `test_a_deeply_nested_payload_is_stored_no_larger_than_its_request`).
- [x] `page.mhtml` is a valid MHTML archive that carries the web fonts the page used and opens offline (`test_page_mhtml_is_an_mhtml_archive_with_the_fonts_the_page_used`).
- [x] `screenshot.png` is Chromium's capture before rotation and the 1-bit conversion (`test_screenshot_png_is_the_capture_before_any_treatment`).
- [x] A later template change does not alter a past job's image or its reprint (`test_a_later_change_cannot_alter_a_past_ticket`).
- [x] A failed write, rename or commit gives 500 and leaves no folder and no job; `.tmp-*` folders are swept at start (`test_a_failed_artifact_write_is_a_500_that_leaves_no_folder_and_no_job`, `test_a_failed_commit_removes_the_renamed_folder_and_stores_no_job`, `test_stale_staging_folders_are_deleted_at_start_and_job_folders_kept`).
- [x] A reprint copies the folder, sends identical bytes, keeps the kind (text stays text) and records `reprint_of`; a job without a folder gets 409 (`test_reprint_copies_the_folder_sends_the_same_bytes_and_records_reprint_of`, `test_a_job_without_its_folder_cannot_be_reprinted`).
- [x] The image route serves `print.png` from the folder; the PNG BLOB and its 30-day prune are gone (`test_job_image_is_the_print_png_of_its_artifact_folder`).
- [x] `printctl show <id>` prints the artifact folder path (`test_show_prints_the_artifact_folder_or_says_it_is_missing`).
- [x] No automatic prune: the folders and records are kept forever.
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T15:29:50+00:00: Built in workspace artifacts__daily-printer, not pushed. Each job is frozen at intake in <database dir>/artifacts/<job id>/: payload.json, source.<ext> (image), page.mhtml, screenshot.png, print.png, job.escpos, meta.json (kind, template, created_at, width, height, render_ms, web_dist_sha256, reprint_of). The folder is staged as .tmp-*, then renamed to the job id inside the insert transaction; a failed write or rename gives 500 with no folder and no job; .tmp-* folders are swept at server start; a crash between rename and commit leaves an orphan folder no job names. Chromium 145 Page.captureSnapshot drops web fonts, so the server adds data:-URL copies of each fetched @font-face rule before the snapshot; the receipt app uses system fonts (Tahoma, Verdana), so its MHTML has none. The PNG BLOB and its 30-day prune are gone; the image route serves print.png. Reprint copies the folder (hard links), sends the source's job.escpos, keeps the kind (text stays text), and records reprint_of; a job without a folder gets 409. printctl show prints the folder (field artifacts on GET /api/jobs/{id}). Disk: 210-280 KB per template ticket, mostly fonts in page.mhtml. Full suite: 588 tests OK; simulate --once OK.
- 2026-10-12T15:53:48+00:00: Review fixes, as new commits on top: payload.json and meta.json are compact JSON (a 900-deep receipt payload had grown about 900 times with indent=2), and job_files runs inside the staging thread, so any failure there is the clean 500; the image route sends nosniff; a failed COMMIT now rolls back and removes the renamed folder (a failed COMMIT can leave the SQLite transaction open, checked); web_dist_sha256 is computed per job; a reprint copies its files; a failed font fetch fails the MHTML snapshot with the font URL; capture_receipt snapshots after measuring; the admin CSS missing-image text matches the Download notice; docs corrected. Tests: 598 OK serially; simulate --once on a free port OK.

## Decisions
