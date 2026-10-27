---
id: 2026-10-26-g3t12q-accept-browser-calls-from-an-allowed-origin
title: Accept browser calls from an allowed origin
status: done
priority: 1
created_date: 2026-10-26
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: null
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
- 2026-10-27T01:00:01+00:00: Local end-to-end run 2026-10-26: real mise-en-place site and catalogue, this server with the redesigned templates, a stand-in for Access, real Chromium CORS, fake printer. Week list: GET /api/me 200, OPTIONS 204, POST 201, printed 24.8 cm. Panqueca (book recipe, 4 components, 14 steps): 201, 46.7 cm. Madalena at 40 portions: 201, 47.1 cm. Stored payloads byte-identical to the page's. QR decodes to the deep link after the quiet-zone fix (omooyt). Not exercised end to end: the accept-long confirm (no real print passes 50 cm); covered by test_cross_origin_browser and the site tests. mise-en-place side merged as PR 17 (4048b3ba).

## Decisions

- 2026-10-26T02:51:38+00:00: decided: the Access application uses 'Bypass options requests to origin', and the print server answers the preflight and sends the CORS headers itself (one place, testable) — easy to change. Findings (developers.cloudflare.com, access-controls/applications/http-apps/authorization-cookie/cors/): without a setting, Access returns 403 to every OPTIONS preflight; CF_Authorization lives on the protected hostname, SameSite default None (Lax also works between sibling subdomains); with no session a fetch fails as a CORS error, so the page opens the print hostname in a new tab to log in, then retries. Operator must flip the bypass toggle in Zero Trust > Access > Applications > the print app > Advanced settings > CORS settings.
- 2026-10-26T03:43:42+00:00: Operator 2026-10-26: the print server's sender hostname is print.felipemoran.com. The mise-en-place page calls https://print.felipemoran.com/api/me and /api/jobs.
