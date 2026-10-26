---
id: 2026-10-26-g3t12q-accept-browser-calls-from-an-allowed-origin
title: Accept browser calls from an allowed origin
status: pending
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

## Decisions
