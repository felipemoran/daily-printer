---
id: 2026-10-25-1z19qx-template-shopping-list-from-mise-en-place
title: 'Template: shopping list from mise-en-place'
status: in-progress
priority: 2
created_date: 2026-10-25
dependencies:
- 2026-10-26-h58jsj-accept-a-print-past-50-cm-up-to-1-m
labels: []
type: feature
parent: null
scope: null
phase: implementing
---

## Description

Operator request 2026-10-25: print the mise-en-place shopping list (~/projects/mise-en-place, 'Lista de compras': the week's ingredients summed and grouped by aisle; the pantry list 'Despensa' has no quantities). The week and the ticks live in the site's localStorage per device, so the print server cannot read them. Open: a Print button on the site that posts the list to the print API, or a server-side week; and whether ticked items print.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-26T02:49:54+00:00: Counterpart in mise-en-place: task tbdq8p (Print button: shopping list).
- 2026-10-26T03:20:11+00:00: Built in changes ywwpzu + wozwly (review fixes). Gatekeeper: round 1 PASS with two should-fix items (list cap 90 below 106 shoppable ingredients; step timer off whole pixels), round 2 ACCEPT. Gates: web lint, web build, full serial suite 670 tests OK (round 1); narrow template tests 62 OK (round 2).
- 2026-10-26T03:25:30+00:00: Sample render (2026-10-26) shows two defects to fix: an amount splits across lines when a row wraps ('creme de leite fresco · 200' / 'ml'); an aisle heading has no gap above it, so the SEMANA list runs into 'AÇOUGUE' and each aisle label touches the rule above.

## Decisions

- 2026-10-26T00:11:25+00:00: Operator decision 2026-10-25: mise-en-place gets a Print button. The site sends the data in a REST request to the print API, and the print system prints it. The server does not read mise-en-place's data or the week state.
- 2026-10-26T02:48:46+00:00: Operator decisions 2026-10-26: (1) The browser POSTs straight to the print server through Cloudflare Access (login on the button); the print server gains CORS for the mise-en-place origin. (2) Printer picker on the page, list fetched from the print server, offline printers included with their status. (3) Content = what mise-en-place #16 share text builds: shopping list = textoSemana() (recipes and portions, every item by aisle with ticked ones included, pantry by name); recipe = textoReceita(r) (portions as shown, ingredients scaled and grouped by component, cook-mode steps). (4) A print past 50 cm returns a warning with its length; the user may accept, and then any template job may print up to a hard cap of 1 m.
- 2026-10-26T04:00:39+00:00: Operator 2026-10-26: adopt the new designs (archive 'recipe templates.zip', design_handoff_receitas_termicas). Contract additions, schemaVersion stays 1 (nothing shipped): recipe.url (ASCII, at most 120 characters, QR + short URL), the site's new deep link https://mise-en-place.felipemoran.com/#receita=<id>; step.uses [{name, amount?}] per step, computed by the site with cook mode's chip code at the card's portions. decided: the 'impresso em' date is the render time in the server's time zone, no payload field — easy to change.
