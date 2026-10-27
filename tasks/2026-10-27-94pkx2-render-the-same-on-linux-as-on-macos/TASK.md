---
id: 2026-10-27-94pkx2-render-the-same-on-linux-as-on-macos
title: Render the same on Linux as on macOS
status: pending
priority: 1
created_date: 2026-10-27
dependencies: []
labels: []
type: fix
parent: null
scope: null
phase: null
---

## Description

First CI run on ubuntu-latest (PR 4) shows the Linux Chromium in the Docker image renders differently from macOS: -webkit-font-smoothing: none is macOS-only, so text is anti-aliased (test_page_alignment AliasedTextTest, LegacyAntiAliasingTest: 243 and 230 grey levels, expected 2); text is wider (test_template_agenda: a 13:00/09:00 label does not fit; test_template_review_queue: tallest queue 52.5 cm over the 50 cm limit). The Compose deployment (PR 3) renders on Linux, so production prints are affected.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions

- 2026-10-27T00:10:59+00:00: Operator 2026-10-26: fix Linux rendering and keep CI on Linux; merge the CI PR and the print PR only when CI is green.
