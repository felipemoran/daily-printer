---
id: 2026-10-28-7vj9sj-decide-daily-printer-visibility-and-branch-protect
title: Decide daily-printer visibility and branch protection
status: operator
priority: 2
created_date: 2026-10-28
dependencies: []
labels: []
type: chore
parent: null
scope: null
phase: null
---

## Description

Operator wants the repo private with branch protection. GitHub Free allows protection only on public repos (mise-en-place, private, got 403 'Upgrade to GitHub Pro or make this repository public'). Options: (1) GitHub Pro, then private, then require the 'checks' job on main; (2) private, no protection; (3) public with protection. Going private breaks the anonymous 'git clone https://github.com/felipemoran/daily-printer.git' in docs/setup-deploy.md and deploy/wizard.sh: every server and Pi then needs a deploy key or gh auth, and the docs need a line.

## Acceptance check

<!-- AC:BEGIN -->
- [ ] The operator picked option 1, 2 or 3.
- [ ] The repo's visibility and protection match that pick.
- [ ] If private: the clone steps in docs/setup-deploy.md and deploy/wizard.sh work with a credential.
<!-- AC:END -->

## Planning

## Execution log

## Decisions
