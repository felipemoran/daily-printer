---
id: 2026-10-12-gnfjvm-demo-one-sample-of-each-template-and-make-targets
title: 'Demo: one sample of each template, and make targets'
status: in-progress
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

Operator request 2026-10-12: make simulate pre-populates the queue with at least one ticket of each template and each kind. Make targets send one sample ticket to the running simulation, so new tickets appear in the admin interface. make simulate prints the /admin URL.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T15:39:43+00:00: make simulate now sends one job per samples/templates/*.json file (discovered at run time), plus text (build.json), image (new samples/test-pattern.png, which replaces the in-memory test pattern) and receipt jobs, alternating home and work, with one progress line per accepted job; --once still checks each job printed (text jobs leave only a .bin, so the summary checks that file). The simulation uses the fixed admin token moranlindo (ADMIN_TOKEN in simulate.py), writes no admin-token file (printctl reads PRINT_ADMIN_TOKEN), and prints the /admin URL, the token and the make demo-<name> command. server_config no longer has MIN_TOKEN_LENGTH; empty and duplicate tokens are still refused. New Makefile targets: make demo (builds web/dist when missing, then runs the simulation) and make demo-<name> (printctl send to DEMO_SERVER, default http://127.0.0.1:8787, printer home), with a curl probe that says to run make demo first and a clear error that lists valid names; make help lists the names. Also fixed: simulate finds uv before it starts the server. Tests: test_make_demo.py (4), new simulation and config tests; full suite 590 OK before the uv fix. --once pre-population took 20 s wall clock. Not tested automatically: make demo building web/dist when it is missing.
- 2026-10-12T15:44:19+00:00: Full suite after the uv fix: 591 tests OK in 271 s.

## Decisions

- 2026-10-12T15:02:03+00:00: Operator decision 2026-10-12: make simulate always uses the admin token moranlindo, stored in the repo (simulate.py), not a random one per run. Remove the 24-character token minimum in server_config everywhere, so the real server may use it too; the operator accepts that anyone past Cloudflare Access could guess a short admin token. The string must never appear in the front end (src/static): the back end alone checks it.
