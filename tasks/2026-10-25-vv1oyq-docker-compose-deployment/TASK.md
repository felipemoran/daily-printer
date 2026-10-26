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
- [x] `make compose-test` passes on this Mac (arm64): it builds the image, prints the 14 template samples plus a text, an image and a receipt job on two fake printers, and checks that each printer's `.bin` equals the job's `job.escpos`. It tears everything down, also on failure.
- [x] `uv run python -m unittest tests.test_compose` passes: services and profiles, loopback-only port, no secret literal, test-only config, healthcheck, `.dockerignore`.
- [x] `docker buildx build --platform linux/amd64 .` builds.
- [ ] The `cloudflared` service runs with a real tunnel token (needs the operator's token).
- [ ] The image runs on the Intel Mac (amd64).
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T00:10:12+00:00: Built the Docker Compose deploy: Dockerfile (Node stage builds web/dist; python:3.12.15-slim-trixie with uv 0.10.8, uv sync --frozen --no-dev, Playwright headless-shell Chromium, the device script env synced at build), runs as non-root user printer (uid 10001); compose.yaml at the repo root with server (127.0.0.1:8787 only, config bind-mounted read-only, named volume daily-printer_data for the database and artifacts, healthcheck on /admin at the container hostname), cloudflared 2026.9.3 under profile tunnel (TUNNEL_TOKEN from .env, untested), two fake printers under profile test, and a check service; deploy/compose-test/ holds the test-only config; make compose-up / compose-down / compose-test. The base is Debian 13 because Chromium's headless shell crashed at launch in about 3% of launches on Debian 12 (0 of 320 on 13). make compose-test passed twice from clean (20 s, 19 s); cold build 78 s, warm 1 s; image 1.76 GB; amd64 build passes (82 s), not run. tests/test_compose.py 12 OK; full suite 645 OK. Docs: setup-deploy.md, Docker Compose section.

## Decisions
