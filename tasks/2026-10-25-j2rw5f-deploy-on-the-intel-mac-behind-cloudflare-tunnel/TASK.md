---
id: 2026-10-25-j2rw5f-deploy-on-the-intel-mac-behind-cloudflare-tunnel
title: Deploy on the Intel Mac behind Cloudflare Tunnel
status: pending
priority: 2
created_date: 2026-10-25
dependencies: []
labels: []
type: feature
parent: null
scope: null
phase: null
---

## Description

Install the print server on the Intel Mac (macOS or Linux) with the Docker Compose setup, behind Cloudflare Tunnel with Cloudflare Access, as docs/planning-print-system-architecture.md plans. Then connect the home printer's device client. Never run so far: the setup wizard, a real Access team, the tunnel.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T00:37:40+00:00: From vv1oyq (2026-10-25): verify on the Intel Mac the cloudflared service with a real TUNNEL_TOKEN, the amd64 image at run time, a backup restore, and config-file ownership on a Linux host (uid 10001 cannot read a 0600 file owned by the host user).

## Decisions
