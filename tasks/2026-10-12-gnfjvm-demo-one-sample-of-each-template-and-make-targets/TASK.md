---
id: 2026-10-12-gnfjvm-demo-one-sample-of-each-template-and-make-targets
title: 'Demo: one sample of each template, and make targets'
status: pending
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: null
---

## Description

Operator request 2026-10-12: make simulate pre-populates the queue with at least one ticket of each template and each kind. Make targets send one sample ticket to the running simulation, so new tickets appear in the admin interface. make simulate prints the /admin URL.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions

- 2026-10-12T15:02:03+00:00: Operator decision 2026-10-12: make simulate always uses the admin token moranlindo, stored in the repo (simulate.py), not a random one per run. Remove the 24-character token minimum in server_config everywhere, so the real server may use it too; the operator accepts that anyone past Cloudflare Access could guess a short admin token. The string must never appear in the front end (src/static): the back end alone checks it.
