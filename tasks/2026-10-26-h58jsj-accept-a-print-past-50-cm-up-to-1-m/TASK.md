---
id: 2026-10-26-h58jsj-accept-a-print-past-50-cm-up-to-1-m
title: Accept a print past 50 cm, up to 1 m
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

Operator decision 2026-10-26: a template job longer than 50 cm is refused with a reply the sender can act on: a stable code and the measured length. The sender may resend the same job with an accept flag; then any template job prints up to a hard cap of 1 m, and past 1 m it is refused outright. First sender: the mise-en-place print button (tasks 1z19qx, vsz7c3; mise-en-place tbdq8p, 33hqgk).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T03:53:01+00:00: Built in unxqst (h58jsj), zoryqy (bjycpj), tlovqq (g3t12q), with review fixes in ypuqrk. Gatekeeper round 2 ACCEPT: web lint, web build, full serial suite 690 tests OK including test_print_server_e2e.

## Decisions
