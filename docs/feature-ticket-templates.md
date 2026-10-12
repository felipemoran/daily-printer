# Feature: print templates

A sender posts data; a template on the Thermal design system (`docs/feature-design-system.md`) lays it out; the pipeline prints it.

## Payload

```json
{ "template": "ticket", "schemaVersion": 1, "data": { "id": "OPS-2481", "title": "…", "status": { "from": "IN REVIEW", "to": "RESOLVED" } } }
```

- `template`: a file name in `web/src/templates/`, without `.tsx`.
- `schemaVersion`: must equal the template's. Raise it when a change to `data` breaks old senders.
- `data`: what the template's `parse` accepts. Unknown fields are refused, so a misspelt optional field fails instead of disappearing.

A payload error raises `TemplateError` (`src/ticket_templates.py`) with a message for the sender, such as `data.fields[1].value: expected string`.

Every template has a sample at `samples/templates/<name>.json`. `tests/test_ticket_templates.py` renders each one.

## Add a template

1. Write `web/src/templates/<name>.tsx`: a default export from `defineTemplate` with `schemaVersion`, `parse` (built from `validate.ts`) and `Component`. `web/src/templates/ticket.tsx` is the example.
2. Render only the content. `render.html` puts it in `<T.Paper print>`, which is the 384-dot `#receipt`.
3. Write the sample `samples/templates/<name>.json`.
4. Run `make test`.

Helper modules in `web/src/templates/` are `.ts`. Every `.tsx` file there is a template.

A wide layout sets `orientation: 'landscape'`: its `#receipt` is 384 dots tall and as wide as it needs, and the pipeline turns it 90° onto the paper. No template uses it yet.

## Print

```bash
make template PAYLOAD=samples/templates/ticket.json
uv run src/scripts/print_template.py samples/templates/ticket.json --no-print   # PNG only
```

| Flag | Effect |
|---|---|
| `--no-print` | Write the PNG to `artifacts/template-<utc-timestamp>/`; do not print. |
| `--no-build` | Use the existing `web/dist`; skip `npm run build`. |
| `--artifact-dir DIR` | Write the PNG to `DIR`. |

A render longer than 4000 dots is refused.

## Code for other callers

`src/ticket_templates.py`: `open_render_page(browser)` once, then `render_template(page, payload)` for each print. One page serves any number of renders, and a failed render leaves the page usable. `template_names()` lists the templates in the last build.

## Design source

`designs/receipt-set-1/` is a verbatim copy of the Claude Design export "Receipt Set 1" (strips 1a to 1n). Open `Receipt Set 1.dc.html` in a browser. Where it and the design system differ, the design system wins.

| Template | Strip |
|---|---|
| `ticket` | 1c ticket update |

## Not done

- QR codes: no QR library is approved yet. The `ticket` template leaves out Set 1's QR slot and the lines beside it.
