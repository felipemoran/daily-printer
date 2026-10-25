---
id: 2026-10-25-vv1oyq-docker-compose-deployment
title: Docker Compose deployment
status: in-progress
priority: 1
created_date: 2026-10-25
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

Operator decision 2026-10-25: run the print server with Docker Compose, and test it on this Mac (Docker Desktop, arm64). Services: the print server (Chromium inside); cloudflared under a 'tunnel' profile (needs a tunnel token); two fake printers under a 'test' profile, so one command reproduces the demo in containers. Real printers keep the native device client on the host: Docker Desktop on macOS cannot pass USB into a container. The image must also build for amd64 (the Intel Mac).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
