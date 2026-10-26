---
id: 2026-10-26-bjycpj-web-senders-see-each-printer-s-status
title: Web senders see each printer's status
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

Operator decision 2026-10-26: the mise-en-place printer picker lists printers from the print server, offline ones included, with their status. GET /api/me (the web sender's endpoint, public printers only) gains online and last_seen per printer; no new endpoint. Consumer: mise-en-place tasks tbdq8p, 33hqgk.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T03:53:01+00:00: Built in unxqst (h58jsj), zoryqy (bjycpj), tlovqq (g3t12q), with review fixes in ypuqrk. Gatekeeper round 2 ACCEPT: web lint, web build, full serial suite 690 tests OK including test_print_server_e2e.

## Decisions
