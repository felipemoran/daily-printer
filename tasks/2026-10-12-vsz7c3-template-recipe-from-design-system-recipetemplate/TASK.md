---
id: 2026-10-12-vsz7c3-template-recipe-from-design-system-recipetemplate
title: 'Template: recipe with amounts from mise-en-place'
status: done
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
- 2026-10-26T03:20:11+00:00: Built in changes ywwpzu + wozwly (review fixes). Gatekeeper: round 1 PASS with two should-fix items (list cap 90 below 106 shoppable ingredients; step timer off whole pixels), round 2 ACCEPT. Gates: web lint, web build, full serial suite 670 tests OK (round 1); narrow template tests 62 OK (round 2).
- 2026-10-26T03:25:31+00:00: Sample render (2026-10-26): an amount splits across lines when a row wraps ('creme de leite fresco · 200' / 'ml'). Fix with the shopping-list one.
- 2026-10-27T00:14:58+00:00: Redesign built in rxzzxt, qxzptv (headline fit), ntputo (long fixture, hyphens). Gatekeeper round 2 ACCEPT: web lint, web build, full serial suite 724 tests OK on macOS.
- 2026-10-27T01:00:00+00:00: Local end-to-end run 2026-10-26: real mise-en-place site and catalogue, this server with the redesigned templates, a stand-in for Access, real Chromium CORS, fake printer. Week list: GET /api/me 200, OPTIONS 204, POST 201, printed 24.8 cm. Panqueca (book recipe, 4 components, 14 steps): 201, 46.7 cm. Madalena at 40 portions: 201, 47.1 cm. Stored payloads byte-identical to the page's. QR decodes to the deep link after the quiet-zone fix (omooyt). Not exercised end to end: the accept-long confirm (no real print passes 50 cm); covered by test_cross_origin_browser and the site tests. mise-en-place side merged as PR 17 (4048b3ba).

## Decisions

- 2026-10-12T06:38:21+00:00: Not in Receipt Set 1 (operator wants only the first iteration, 1a-1n). Gap: no template for this print type.
- 2026-10-26T00:11:25+00:00: Operator decision 2026-10-25: mise-en-place gets a Print button. The site sends the data in a REST request to the print API, and the print system prints it. The server does not read mise-en-place's data or the week state.
- 2026-10-26T02:48:46+00:00: Operator decisions 2026-10-26: (1) The browser POSTs straight to the print server through Cloudflare Access (login on the button); the print server gains CORS for the mise-en-place origin. (2) Printer picker on the page, list fetched from the print server, offline printers included with their status. (3) Content = what mise-en-place #16 share text builds: shopping list = textoSemana() (recipes and portions, every item by aisle with ticked ones included, pantry by name); recipe = textoReceita(r) (portions as shown, ingredients scaled and grouped by component, cook-mode steps). (4) A print past 50 cm returns a warning with its length; the user may accept, and then any template job may print up to a hard cap of 1 m.
- 2026-10-26T02:59:01+00:00: decided: string and list caps come from the real catalogue maxima with headroom; they bound payload size and prevent clipping, not length. The length guard decides length and refuses a print past the limit with a clear 422 — easy to change. Reason: a realistic book recipe (25 ingredients, 20 steps of 150 characters) renders about 90 cm, and caps sized to keep every payload under 1 m would refuse real recipes.
- 2026-10-26T04:00:39+00:00: Operator 2026-10-26: adopt the new designs (archive 'recipe templates.zip', design_handoff_receitas_termicas). Contract additions, schemaVersion stays 1 (nothing shipped): recipe.url (ASCII, at most 120 characters, QR + short URL), the site's new deep link https://mise-en-place.felipemoran.com/#receita=<id>; step.uses [{name, amount?}] per step, computed by the site with cook mode's chip code at the card's portions. decided: the 'impresso em' date is the render time in the server's time zone, no payload field — easy to change.
- 2026-10-26T12:29:31+00:00: Operator 2026-10-26 on the redesign renders: headlines never break inside a word; the whole headline shrinks to one size until every word fits (never one word alone); multi-word titles wrap between words. Applies to the shopping-list COMPRAS too.
- 2026-10-27T00:02:56+00:00: decided: a hyphenated compound (pimenta-do-reino) counts as one word in a headline, so it never breaks at the hyphen and the whole headline shrinks instead (non-breaking hyphen) — easy to change. Review found the redesign made MADALENA 47.1 cm, which silently dropped the 50-100 cm long-print tests; a dedicated fixture with a height-band test replaces it there.
