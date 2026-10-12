---
id: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
title: Ticket templates on the Thermal design system — orchestrator mission log
status: operator
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: null
scope: null
phase: null
---

## Description

Operator goal (2026-10-12): implement the ticket types (named templates with typed data) on the Thermal design system, for the print-system session to integrate later. Coordinate the payload/render contract with the print-system session (print-system-daily-printer-65, workspace .workspaces/print-system__daily-printer). Design source: Receipt Set 1 (tickets 1a-1n, first of three iterations) in Claude Design project d7dceba5-0ce2-4464-ad5f-9ede879d70a7; only the first iteration is wanted. Iteration happens locally on the work Mac (full stack + USB printer); no freeform layout DSL.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:39:32+00:00: Infra builder dispatched in .workspaces/tpl-infra (base mysqmu). Set 1 spec gathered (14 strips; 1g agenda, 1k rotated banner and 1m hero row need new layout; 1h stays a raster preview of TextMode).
- 2026-10-12T07:17:24+00:00: Retro note: I based the fit-guard verify merge and two builder rebases on xzslrz while it was still my live @; a bacon write rewrote it mid-run (tasks/ only). Froze it with jj new. Manual §8 already warns; add 'freeze the close-out before building ANY merge or rebase on it' in the retro.
- 2026-10-12T08:03:25+00:00: All 14 Set 1 templates integrated in merge nrlvsn (plus receipt wrap fix). Next: final gate, then validator cleanup + render_text (parallel), test build once, docs.
- 2026-10-12T08:08:05+00:00: Final template gate on nrlvsnow: 187 tests green twice; 14 templates render (sprint 384 wide); daily receipt OK. Sent to the print-system session as a stable point.
- 2026-10-12T08:13:14+00:00: Retro: repeated the live-@ foot-gun (verify/integration merge parented on @). Caught before any write; froze it with jj new. Retro fix: never pass @ as a merge parent; jj new a described child first.
- 2026-10-12T08:28:10+00:00: Print-system session asks how to land. Proposed (a): my chain as its own draft PR to main first, theirs after. Needs the operator's decision and SSH approval to push; staging locally meanwhile.
- 2026-10-12T08:34:36+00:00: Final gate on mvmknm: 207 tests green twice, 0 skips; 14 templates; --text job 860 bytes (ESC @ + 855-byte body + 3 LF). Final review: no blockers, 5 should-fix (early-wave conventions, duplicate parsers/font helper, test skips/visibility); fix round in tpl-final. Two scope requests filed as drafts.
- 2026-10-12T08:54:36+00:00: Final state (2026-10-12): all 14 Receipt Set 1 templates + render infrastructure + guards + render_text integrated in final merge vntkpt; final gate 212 tests green twice, 0 skips; every sample renders 384 wide, byte-identical across the last two gates. Not pushed: pushing needs the operator's SSH approval. Landing plan agreed with the print-system session: this chain as its own draft PR to main first (bookmark felipe/design-system-templates), theirs after (their line already merged an earlier stable point). Open for the operator: tasks 8-task cap; landing/push; hardware checks for native text (code page 0 for █ ░, ESC 3 24, GS B / GS !, column-32 wrap, FS .); design-system paper checks in design-system/verify.md; follow-up drafts (design-system fixes for Claude Design, image templates, UTC ages, daily_print flag combos, shared test helper, Recipe/Meme). Orchestrator manual lesson committed in the bacon repo (slouol, workspace orchestrator-live-commit__bacon), not pushed.
- 2026-10-12T09:20:44+00:00: Follow-up from the print-system session: nkvroo (check_envelope refuses RecursionError and payloads nested > 32 levels as TemplateError — Playwright fails from ~500 levels; public TEXT_FEED in ticket_templates.py imported by print_template.py). In review + test run.
- 2026-10-12T09:28:59+00:00: nkvroo gates: 214 tests green, 0 skips. Review: page.evaluate HANGS at ~150–300 levels (no exception, timeout does not apply) — cap 32 has ~4x headroom; comment fix + depth-walk-first simplification + deep-dict test + docs requested.
- 2026-10-12T09:31:08+00:00: Follow-up integrated linearly: txrwsr → nkvroo (deep payloads are sender faults; TEXT_FEED) → zpwpwz (depth walk first, stops past 32; comment documents the 145–300-level page.evaluate hang; deep-dict test; docs) → this bookkeeping commit. Bookmark felipe/design-system-templates moved here.

## Decisions

- 2026-10-12T06:36:04+00:00: decided: implement the 8 templates of the mirrored bundle now (operator said implement the bundle's ticket types if present); Receipt Set 1 (1a-1n) extends or replaces them when exported — easy to change
- 2026-10-12T06:36:04+00:00: Contract agreed with print-system session (2026-10-12): kind 'template', payload {template, schemaVersion, data}. Python API in src/ticket_templates.py: open_render_page(browser) -> Page, render_template(page, payload, *, max_height_dots) -> PIL Image mode '1', 384 wide, print profile applied; TemplateError(ValueError) for sender-fixable failures (unknown template, invalid data, render failure, too tall; mapped to HTTP 422); template_names(). Validation lives only here. Fail fast: React error boundary, explicit few-second timeouts, #receipt.offsetHeight > max_height_dots checked before the screenshot. Page reuse must leave no leftovers; a failed render leaves the page usable. Keep unchanged: raster_capture.capture_receipt; print_profile capture_options/load_gray/to_bitmap/join_js/DEFAULT_PROFILE; photo_dither prepare/dither; web app /payload.json, #receipt, .receipt--error.
- 2026-10-12T06:36:05+00:00: decided: no schema library yet (zod/ajv need operator approval); each template validates its data with small shared helpers and reports a field path — easy to change
- 2026-10-12T06:36:05+00:00: decided: QR codes are left out of templates until a QR generator library is approved; filed as a draft — easy to change
- 2026-10-12T06:38:23+00:00: decided: the template set is Receipt Set 1 strips 1a-1n (14). Layout and content come from Set 1; styling comes from the Thermal design system (components, tokens, real greys dithered by the pipeline), which supersedes Set 1's hand-made dot-pattern fills — easy to change
- 2026-10-12T06:38:23+00:00: Agreed with print-system session: 1h stays a raster preview for now; a native render_text(payload) -> bytes is a new job kind for the operator to decide. 1k is rotated inside render_template so the output stays 384 wide.
- 2026-10-12T06:39:31+00:00: decided: 1a test page is implemented as a no-data template with design-system tones in place of Set 1's hand-made pattern swatches (the Test* strips via preview.html stay the detailed calibration tool) — easy to change
- 2026-10-12T06:39:32+00:00: decided: template builders run in waves of up to 4; each self-checks with lint, tsc and a single render of its own sample (one Chromium process, no unittest runs). Only the verifier runs the test suite, once per wave on a merge — easy to change
- 2026-10-12T06:46:49+00:00: Operator decisions (2026-10-12): QR library OK if industry standard and well maintained; 1h native text approved as a late, low-priority fallback; daily receipt stays, Tasks template added beside it for comparison; Recipe/Meme deferred (draft).
- 2026-10-12T07:02:35+00:00: decided: review-queue ages are whole days (ageDays); sub-day ages print 0D instead of strip 1i's hours. Adding an hours field is the operator's call — easy to change
- 2026-10-12T07:06:58+00:00: Bug class from 1e review, propagated to every builder: text in a fixed-width design-system cell is silently clipped (overflow:hidden) and prints a wrong value while the render succeeds. Guard: format to fit, bound labels in the parser, and test scrollWidth <= clientWidth on edge payloads.
- 2026-10-12T07:11:28+00:00: Bug class from 1i re-review, propagated: caps must keep a VALID worst-case payload (all lists at cap, strings at max length in the widest glyph, maximum wrapping) under the 4000-dot render limit; every template tests its worst-case height.
- 2026-10-12T07:12:55+00:00: decided: review-queue bounds title ≤ 64, area ≤ 10, diff counts ≤ 999,999, list ≤ 20, so the worst case stays under 4000 dots. A 10-char area refuses names like 'billing-api' — easy to change (trade against title length or list cap)
- 2026-10-12T07:17:05+00:00: decided: no character-set restrictions on free text (names need accents); pathological wide glyphs are refused loudly by the 4000-dot limit and the render-time fit guard. Worst-case height tests use W and CJK glyphs — easy to change
- 2026-10-12T07:17:05+00:00: decided: habit log — skipped days break a streak and are excluded from completion; completion and uptime percentages round DOWN so 'all done / fully up' is never shown when it is not true — easy to change
- 2026-10-12T07:19:55+00:00: Bug class from 1n review, propagated: a render can resolve before layout settles (fresh page, fallback-font glyphs), so the capture differs from the measured receipt. Guard: render_template compares measured vs captured length and refuses; templates that measure text await the faces for the actual text; tests include a fresh page with non-Latin text.
- 2026-10-12T07:26:12+00:00: Root cause (1n): glyphs absent from the bundled fonts use a system fallback face that Chrome may switch when Playwright's screenshot resizes the viewport, changing layout during capture. Structural fix first: size the viewport to the receipt before measuring/capturing. Refusing non-Latin text is the fallback and needs the operator's call.
- 2026-10-12T07:35:58+00:00: decided: 1h's text lines come from ONE pure TS line model in the web app; the raster template renders it with T.TextMode, and the later render_text evaluates the same function in the page and encodes ESC/POS in Python, so preview and native print share line breaks by construction. render_text therefore needs a page: render_text(page, payload) -> bytes (to agree with the print-system session) — easy to change
- 2026-10-12T07:42:04+00:00: decided: sprint 'day' may exceed 'of' (overrun sprints are real); leaderboard keeps a 10-person cap and takes ranks from list order — easy to change
- 2026-10-12T07:46:46+00:00: decided: 1h text mode truncates long values with '~' in fixed columns (documented), keeps empty-section headers (FAILURES (0)) as uptime does, prints 'since #N' only when the sender sends it, and takes the build name (e.g. NIGHTLY) as optional data — easy to change
- 2026-10-12T07:47:44+00:00: Bug class from 1g review, propagated: never decide text fit with a character-width MODEL; measure the rendered text after fonts load (focus.tsx pattern). A model that under-counts turns a valid payload into a refused print under the fit guard.
- 2026-10-12T08:04:27+00:00: Contract between the cleanup tasks: a template's server-side failure (e.g. a font that did not load) throws an Error with name 'ServerFault'; render-main rejects with the prefix 'server fault: '; render_template raises RuntimeError (not TemplateError) for that prefix.
- 2026-10-12T08:48:06+00:00: decided: the tasks template prints at most 8 tasks (+N MORE IN TODOIST), so ANY valid payload fits one print (emoji worst case 3935 dots). Alternative for the operator: ~20 tasks with a loud refusal on pathological days. One constant in tasks.tsx + src/tasks_template.py — easy to change
- 2026-10-12T09:20:44+00:00: decided: payloads nested more than 32 levels deep are refused (sender fault, 422); the deepest sample is 6 and Playwright breaks at ~500 — easy to change
