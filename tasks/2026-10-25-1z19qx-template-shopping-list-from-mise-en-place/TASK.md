---
id: 2026-10-25-1z19qx-template-shopping-list-from-mise-en-place
title: 'Template: shopping list from mise-en-place'
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

Operator request 2026-10-25: print the mise-en-place shopping list (~/projects/mise-en-place, 'Lista de compras': the week's ingredients summed and grouped by aisle; the pantry list 'Despensa' has no quantities). The week and the ticks live in the site's localStorage per device, so the print server cannot read them. Open: a Print button on the site that posts the list to the print API, or a server-side week; and whether ticked items print.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions

- 2026-10-26T00:11:25+00:00: Operator decision 2026-10-25: mise-en-place gets a Print button. The site sends the data in a REST request to the print API, and the print system prints it. The server does not read mise-en-place's data or the week state.
