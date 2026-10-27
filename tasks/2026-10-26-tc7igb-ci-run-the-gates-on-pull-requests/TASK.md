---
id: 2026-10-26-tc7igb-ci-run-the-gates-on-pull-requests
title: 'CI: run the gates on pull requests'
status: done
priority: 1
created_date: 2026-10-26
dependencies: []
labels: []
type: chore
parent: null
scope: null
phase: null
---

## Description

Operator request 2026-10-26: daily-printer has no CI (no .github/, no runs). Add a GitHub Actions workflow that runs the real gates on every pull request and on push to main: npm ci, web lint and build, Playwright Chromium, and the full unittest suite (make test). Mirror mise-en-place's checks.yml style (pinned action SHAs, uv, Node 24, Playwright cache, timeout). Merge before the print PR, so that PR gets checked.

## Acceptance check

<!-- AC:BEGIN -->
- [ ] .github/workflows/checks.yml runs on every pull_request and on push to main.
- [ ] It runs npm ci, web lint and web build, uv sync --locked, Playwright Chromium at the locked version, and make test.
- [ ] Its first run on GitHub passes.
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T23:58:22+00:00: Workflow added in ultpzz (Python from .python-version 3.12; four actions pinned by SHA). Review ACCEPT, two nits fixed. Static checks only: YAML parses, SHAs match tags. The first GitHub run is the proof; opening a draft PR from felipe/ci-checks.

## Decisions
