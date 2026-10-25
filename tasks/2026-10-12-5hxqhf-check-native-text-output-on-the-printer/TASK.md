---
id: 2026-10-12-5hxqhf-check-native-text-output-on-the-printer
title: Check native text output on the printer
status: draft
priority: 2
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: null
scope: null
phase: null
---

## Description

Native text output (render_text in src/ticket_templates.py) has byte-level tests only. Nothing ran on the MPT-II. Print: uv run src/scripts/print_template.py samples/templates/build.json --text. Check each assumption the byte framing makes: code page 0 prints the block glyphs (0xDB full, 0xB0 light); ESC 3 24 gives the expected line spacing; GS B (reverse) and GS ! 0x11 (double size) work; a full 32-column line does not add a blank line from auto-wrap; FS . (leave Kanji mode) is needed or harmless.

## Acceptance check

A photo of the print is attached to this task. Each assumption above is recorded as confirmed or wrong. Each wrong one has a fix with a test.

## Planning

## Execution log

## Decisions
