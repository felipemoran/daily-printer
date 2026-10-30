---
id: 2026-10-25-j2rw5f-deploy-on-the-intel-mac-behind-cloudflare-tunnel
title: Deploy on the Intel Mac behind Cloudflare Tunnel
status: operator
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
- 2026-10-28T00:15:24+00:00: 2026-10-27 local half done (operator chose: live end to end, Docker Compose, two fake printers). Checkout .workspaces/deploy__daily-printer on main 8dc5e236; config ~/print-server/config.toml (0600) with printers cozinha and escritorio (public), allowed_origins mise-en-place; .env (0600); make compose-up healthy on 127.0.0.1:8787; two LaunchAgents com.daily-printer.device.{cozinha,escritorio} with --fake ~/fake-printers/<id>, both online; test prints landed as PNGs. Docker runs with DOCKER_CONFIG=~/print-server/docker-config (no credsStore prompt). Waiting on the operator: run the Cloudflare wizard (/private/tmp/claude-501/-Users-felipemoran-projects-daily-printer--workspaces-mise-print--daily-printer/1cf5ce46-489b-454d-a6ce-f83e88f70d80/scratchpad/cloudflare-wizard.sh): team domain, tunnel + token, hostname print.felipemoran.com -> http://server:8787, Access app, CORS bypass OPTIONS, AUD tag. Then: make compose-up again (real [access]), docker compose --profile tunnel up -d, check the Access redirect, print from the live site, check the PNG.
- 2026-10-30T22:54:07+00:00: The Cloudflare wizard now lives beside this task: 2026-10-25-j2rw5f-deploy-on-the-intel-mac-behind-cloudflare-tunnel/cloudflare-wizard.sh. Run it from the repo root: tasks/2026-10-25-j2rw5f-deploy-on-the-intel-mac-behind-cloudflare-tunnel/cloudflare-wizard.sh. The scratchpad path above is gone.

## Decisions
