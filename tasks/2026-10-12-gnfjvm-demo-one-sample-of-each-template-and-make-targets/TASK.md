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
- [x] `make simulate --once` sends one job per `samples/templates/*.json` file plus text, image and receipt jobs over both printers, and every job prints (`test_once_prints_every_sample_on_two_fake_printers_and_leaves_no_process`)
- [x] A new template sample file is picked up with no code change (`test_sample_jobs_are_every_template_file_then_text_image_and_receipt`)
- [x] `make demo-<name>` sends that sample with the simulation admin token; an unknown name, a name with shell code, a missing curl and a stopped simulation each give a clear error (`tests/test_make_demo.py`)
- [x] `make help` lists `demo` and, next to it, `demo-<name>` with every name
- [x] `make demo` says to run `make setup` when `web/node_modules` is missing (`test_demo_without_web_dependencies_says_to_run_make_setup`)
- [ ] `make demo` builds `web/dist` when it is missing: checked by reading the recipe only, no automated test
- [x] The simulation uses the admin token `moranlindo` and prints `<base>/admin`, the token and the `make demo-<name>` command
- [x] The server config accepts a short token and refuses an empty one (`test_a_short_token_loads_and_an_empty_one_is_refused`)
- [x] No file under `src/static/` contains the admin token (`test_the_admin_token_never_reaches_the_front_end`)
- [x] A stop ends the server cleanly, well under `STOP_TIMEOUT` (`test_sigterm_while_running_stops_the_server_and_both_devices_and_exits_0`)
- [x] The full test suite passes (594 tests, 2026-10-12)
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T15:39:43+00:00: make simulate now sends one job per samples/templates/*.json file (discovered at run time), plus text (build.json), image (new samples/test-pattern.png, which replaces the in-memory test pattern) and receipt jobs, alternating home and work, with one progress line per accepted job; --once still checks each job printed (text jobs leave only a .bin, so the summary checks that file). The simulation uses the fixed admin token moranlindo (ADMIN_TOKEN in simulate.py), writes no admin-token file (printctl reads PRINT_ADMIN_TOKEN), and prints the /admin URL, the token and the make demo-<name> command. server_config no longer has MIN_TOKEN_LENGTH; empty and duplicate tokens are still refused. New Makefile targets: make demo (builds web/dist when missing, then runs the simulation) and make demo-<name> (printctl send to DEMO_SERVER, default http://127.0.0.1:8787, printer home), with a curl probe that says to run make demo first and a clear error that lists valid names; make help lists the names. Also fixed: simulate finds uv before it starts the server. Tests: test_make_demo.py (4), new simulation and config tests; full suite 590 OK before the uv fix. --once pre-population took 20 s wall clock. Not tested automatically: make demo building web/dist when it is missing.
- 2026-10-12T15:44:19+00:00: Full suite after the uv fix: 591 tests OK in 271 s.
- 2026-10-12T16:10:09+00:00: Review fixes: simulate main() now saves and restores the stop-signal handlers, and Children.stop no longer sets them, so an in-process caller keeps its own handlers (the uv test and the Ctrl-C test now run in one process with no signal mock). Children unblock the stop signals in preexec_fn: before, they inherited the blocked mask, so every stop waited STOP_TIMEOUT (10 s) and then SIGKILLed; now the server logs stopping and stopped about 8 ms after the last job, and --once takes 12.6 s instead of 22.7 s. Makefile: the demo name is validated in make before any shell runs (make 'demo-$(cmd)' no longer runs cmd), a missing curl is named, make demo says to run make setup when web/node_modules is missing, and make help prints demo-<name> next to demo. Docs and the print_device --fake help now say that a text job leaves only a .bin. Tests: simulation, demo, config and device modules 65 OK; full suite 594 OK in 257 s.

## Decisions

- 2026-10-12T15:02:03+00:00: Operator decision 2026-10-12: make simulate always uses the admin token moranlindo, stored in the repo (simulate.py), not a random one per run. Remove the 24-character token minimum in server_config everywhere, so the real server may use it too; the operator accepts that anyone past Cloudflare Access could guess a short admin token. The string must never appear in the front end (src/static): the back end alone checks it.
