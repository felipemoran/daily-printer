---
id: 2026-10-26-g3t12q-accept-browser-calls-from-an-allowed-origin
title: Accept browser calls from an allowed origin
status: in-progress
priority: 1
created_date: 2026-10-26
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

Operator decision 2026-10-26: the mise-en-place page (https://mise-en-place.felipemoran.com) calls GET /api/me and POST /api/jobs straight from the browser, authenticated by Cloudflare Access. Needs a configured list of allowed origins, credentialed CORS headers and an OPTIONS preflight answer for those routes, and a check_same_site exception for an allowed Origin only. Every other cross-site POST stays refused. Depends on how Access handles the preflight and the cookie (research pending).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T03:43:42+00:00: Gatekeeper round 1 BLOCK: a printctl test fake rejected accept_long (suite red, 1 of 690); CORS keyed on path only exposed GET /api/jobs (admin list) to the allowed origin. Fixes sent back to the builder with three nits (Vary always, default/out-of-range ports, typed limit).
- 2026-10-26T03:53:02+00:00: Built in unxqst (h58jsj), zoryqy (bjycpj), tlovqq (g3t12q), with review fixes in ypuqrk. Gatekeeper round 2 ACCEPT: web lint, web build, full serial suite 690 tests OK including test_print_server_e2e.
- 2026-10-26T04:46:29+00:00: Browser-level test added in qvxrnm (tests/test_cross_origin_browser.py): real Chromium, a page on an allowed and a disallowed origin, a proxy standing in for Access. 6 tests OK; with the CORS hook broken, the 4 allowed-origin tests fail.

## Decisions

- 2026-10-26T02:51:38+00:00: decided: the Access application uses 'Bypass options requests to origin', and the print server answers the preflight and sends the CORS headers itself (one place, testable) — easy to change. Findings (developers.cloudflare.com, access-controls/applications/http-apps/authorization-cookie/cors/): without a setting, Access returns 403 to every OPTIONS preflight; CF_Authorization lives on the protected hostname, SameSite default None (Lax also works between sibling subdomains); with no session a fetch fails as a CORS error, so the page opens the print hostname in a new tab to log in, then retries. Operator must flip the bypass toggle in Zero Trust > Access > Applications > the print app > Advanced settings > CORS settings.
- 2026-10-26T03:43:42+00:00: Operator 2026-10-26: the print server's sender hostname is print.felipemoran.com. The mise-en-place page calls https://print.felipemoran.com/api/me and /api/jobs.
