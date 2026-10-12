---
id: 2026-10-12-l0w88g-render-job-rendererror-for-a-non-image-upload-show
title: 'render_job: RenderError for a non-image upload shows ''<_io.BytesIO object at 0x...>'' to the sender'
status: draft
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
scope: null
phase: null
---

## Description

Found by the printctl review. The 422 text should be a plain sentence such as 'the upload is not an image Pillow can read'. Small fix in src/render_job.py and its test.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions
