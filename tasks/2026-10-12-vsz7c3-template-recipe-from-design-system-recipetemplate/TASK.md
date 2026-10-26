---
id: 2026-10-12-vsz7c3-template-recipe-from-design-system-recipetemplate
title: 'Template: recipe with amounts from mise-en-place'
status: pending
priority: 2
created_date: 2026-10-12
dependencies:
- 2026-10-26-h58jsj-accept-a-print-past-50-cm-up-to-1-m
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

Operator request 2026-10-25: print a mise-en-place recipe with its ingredient amounts and its steps (~/projects/mise-en-place, dados/receitas/<id>.json, schema in dados/esquemas/receita.schema.json). Amounts must follow the chosen portions, as the site's card shows them; book recipes carry componentes with their own quantidades. The design system's RecipeTemplate preview is a starting point for the layout. Open: who sends the payload (the site at the shown portions, or the server from catalogo.json), and long recipes past the 50 cm print limit.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:46:48+00:00: Operator (2026-10-12): not in this run; do later.
- 2026-10-26T02:49:54+00:00: Counterpart in mise-en-place: task 33hqgk (Print button: recipe with amounts).

## Decisions

- 2026-10-12T06:38:21+00:00: Not in Receipt Set 1 (operator wants only the first iteration, 1a-1n). Gap: no template for this print type.
- 2026-10-26T00:11:25+00:00: Operator decision 2026-10-25: mise-en-place gets a Print button. The site sends the data in a REST request to the print API, and the print system prints it. The server does not read mise-en-place's data or the week state.
- 2026-10-26T02:48:46+00:00: Operator decisions 2026-10-26: (1) The browser POSTs straight to the print server through Cloudflare Access (login on the button); the print server gains CORS for the mise-en-place origin. (2) Printer picker on the page, list fetched from the print server, offline printers included with their status. (3) Content = what mise-en-place #16 share text builds: shopping list = textoSemana() (recipes and portions, every item by aisle with ticked ones included, pantry by name); recipe = textoReceita(r) (portions as shown, ingredients scaled and grouped by component, cook-mode steps). (4) A print past 50 cm returns a warning with its length; the user may accept, and then any template job may print up to a hard cap of 1 m.
