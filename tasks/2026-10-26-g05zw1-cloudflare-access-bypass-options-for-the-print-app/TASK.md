---
id: 2026-10-26-g05zw1-cloudflare-access-bypass-options-for-the-print-app
title: 'Cloudflare Access: bypass OPTIONS for the print app'
status: operator
priority: 2
created_date: 2026-10-26
dependencies: []
labels: []
type: chore
parent: null
scope: null
phase: null
---

## Description

Operator action, deferred 2026-10-26. The mise-en-place Print button calls https://print.felipemoran.com from the browser. Without this setting, Cloudflare Access answers every CORS preflight with 403 and no print reaches the server. In Zero Trust > Access > Applications > the print.felipemoran.com app > Advanced settings > CORS settings, turn on 'Bypass options requests to origin'. Keep the app's cookie SameSite at None (the default) or Lax. The print server answers the preflight itself (task g3t12q); see docs/setup-deploy.md, section 'Calls from a page on another site'. Also needs the server deployed (task j2rw5f) and [access] allowed_origins = ["https://mise-en-place.felipemoran.com"] in its config.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
