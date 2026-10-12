---
id: 2026-10-12-8jwfzz-web-npm-ci-reports-10-vulnerabilities-1-low-2-mode
title: 'web/: npm ci reports 10 vulnerabilities (1 low, 2 moderate, 7 high)'
status: in-progress
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
scope: null
phase: implementing
---

## Description

Seen by the wave 4/5 gate after the design-system merge. Not investigated. Needs operator approval before any dependency change (CLAUDE.md prior-art rule).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T14:59:43+00:00: npm audit in web/ found 10 vulnerabilities (1 low, 2 moderate, 7 high), all in dev tooling: vite and its postcss/nanoid/source-map-js chain, eslint and typescript-eslint (brace-expansion, js-yaml, @humanfs/node), and eslint-plugin-react-hooks (@babel/core, browserslist, baseline-browser-mapping). None was in the shipped runtime dependencies (react, react-dom, qrcode-generator). npm audit fix without --force cleared all 10; only package-lock.json changed, within the existing package.json ranges. The main moves were vite 8.0.8 to 8.3.4 and rolldown 1.0.0-rc.15 to 1.2.13. No major bump and no overrides were needed. The render baseline stayed byte-identical: all 14 samples/templates payloads produce the same render_template bitmaps, and the build template's render_text produces the same bytes. The baseline was confirmed deterministic by two runs before the fix. npm run build and npm run lint pass. web/ has no npm test script. The Python suite (uv run python -m unittest discover -s tests) ran 579 tests, all OK.

## Decisions
