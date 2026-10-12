# Feature: print templates

A sender posts data. A template on the Thermal design system (`docs/feature-design-system.md`) lays it out. The pipeline prints it.

## Templates

Each template is one Receipt Set 1 strip (see *Design source*). The name links to its sample payload.

| Template | Strip | Rules a sender would otherwise guess wrong |
|---|---|---|
| [`test-page`](../samples/templates/test-page.json) | 1a test page | All fields are optional. |
| [`tasks`](../samples/templates/tasks.json) | 1b tasks | At most 8 tasks. `more` counts the tasks left out, and the OPEN tile adds it. Done tasks print after open ones. |
| [`ticket`](../samples/templates/ticket.json) | 1c ticket update | `qr.text` is ASCII, at most 120 characters: percent-encode a URL. |
| [`incident`](../samples/templates/incident.json) | 1d incident | The template prints the `#` before `id`, and drops a leading `#` that the sender sent. |
| [`report`](../samples/templates/report.json) | 1e weekly report | Amounts are numbers from 0 to 1e12. Each prints in the most precise form that fits its cell, for example `12K`. An odd number of KPIs prints one per row. |
| [`uptime`](../samples/templates/uptime.json) | 1f uptime | `hours` is 24 characters: `o` ok, `d` degraded, `x` down. `uptimePct` is truncated to two decimals: 99.999 prints `99.99%`. |
| [`agenda`](../samples/templates/agenda.json) | 1g agenda | Times are `HH:MM`. Every event must lie inside `dayStart` to `dayEnd` (at most 14 hours) and last 10 minutes or more. A third event that overlaps two others is refused. A title that does not fit its box prints in an UNLABELLED list. |
| [`build`](../samples/templates/build.json) | 1h build | Prints as native text too (see *Native text output*). Values in fixed columns are cut with `~`. The URL and failure titles wrap. Text outside ASCII loses its accents, or prints as `?`. |
| [`review-queue`](../samples/templates/review-queue.json) | 1i review queue | Rows print oldest first (largest `ageDays`). Ties keep the sender's order. An age over 2 days gets a STALE tag. |
| [`habits`](../samples/templates/habits.json) | 1j habits | `days` is 28 to 31 characters: `1` done, `0` missed, `-` skipped. Every habit has the same number of days. Skipped days do not count for completion. Completion is floored. |
| [`sprint`](../samples/templates/sprint.json) | 1k sprint | A landscape banner: it prints sideways, 384 dots tall and as long as its columns. At most 6 columns of 6 cards each. Cards stack 3 high. |
| [`briefing`](../samples/templates/briefing.json) | 1l briefing | Temperatures are whole numbers from -99 to 199. |
| [`leaderboard`](../samples/templates/leaderboard.json) | 1m leaderboard | Ranks come from list order: the first person is #1. The template does not sort. Percentages are floored: 99.6 prints `99%` and does not reach the quota. |
| [`focus`](../samples/templates/focus.json) | 1n focus | None. |

## Payload

```json
{ "template": "ticket", "schemaVersion": 1, "data": { "id": "OPS-2481", "title": "…", "status": { "from": "IN REVIEW", "to": "RESOLVED" } } }
```

- `template`: a template name from the table.
- `schemaVersion`: must equal the template's. Raise it when a change to `data` breaks old senders.
- `data`: what the template's `parse` accepts. Unknown fields are refused, so a misspelt optional field fails instead of disappearing.
- The whole payload is at most 64 KiB (65536 bytes of UTF-8 JSON). Every list in `data` has a maximum length.

## Python API

`src/ticket_templates.py` is what a print server calls. It needs a built `web/dist` (`make web-build`).

| Call | Does |
|---|---|
| `template_names()` | The template names in the last build. |
| `check_envelope(payload)` | Checks the envelope and the size limit without a browser. It does not check `schemaVersion` against the template. |
| `open_render_page(browser)` | Opens a Playwright page on `render.html`. Open it once and reuse it: a failed render leaves it usable. The page loads files from `web/dist` only, never from the network. |
| `render_template(page, payload, *, max_height_dots=4000)` | The print as a mode `"1"` PIL image, 384 dots wide. `max_height_dots` sets the length limit (see *Render guards*). |
| `render_text(page, payload)` | The print as native ESC/POS text bytes (see *Native text output*). |

Both render calls run `check_envelope` first. They raise two kinds of error:

- `TemplateError` (a `ValueError`): a sender fault. The message tells the sender what to fix, for example `data.fields[1].value: expected string`. A server answers HTTP 422.
- `RuntimeError`: a server fault, for example a stale build or a font that did not load. A template raises one in the page with `serverFault(message)` (`web/src/templates/faults.ts`), and its message starts with `server fault: `. A server answers HTTP 500.

Playwright errors pass through unchanged.

A render that does not finish within 3 seconds raises `TemplateError`. The page cannot stop a render that is busy, so the size limit and the list maxima keep every render short.

## Render guards

`render_template` refuses a print that would come out wrong, because a clipped or cut print looks like a good one. Each refusal is a `TemplateError`:

- **Length:** a print longer than `max_height_dots` (default 4000 dots, 50 cm) is refused before the screenshot.
- **Fit:** a box that clips its text, text that spills out of its block, or anything past the 384-dot paper edge is refused, because a clipped value prints as a different value. In landscape the paper edge is the bottom of the layout. The message quotes the text: `text does not fit: "123,456" is wider than its 52px cell`.
- **Capture length:** the length is measured before the screenshot, in it, and after it. A change refuses the print, because the screenshot keeps its first clip and the print would lose its end or end in a band of page background.
- **Viewport sizing:** this one prevents a refusal. The page is resized to cover the whole receipt before it is measured, because a screenshot past the viewport can make Chrome draw missing glyphs from another system font and reflow the page.

## Native text output

A template with a text mode prints in the printer's own Font A (32 columns), not as a raster. Only `build` has one. `render_text` raises `TemplateError` for any other template. The text breaks where the raster preview breaks.

`render_text` returns the body only. The caller adds `ESC @` (initialize) before it and the paper feed after it. The body is:

1. `FS .`: leave Chinese double-byte mode, which some printers start in.
2. `ESC 3 24`: a 24-dot line.
3. `ESC t 0`: code page 0. `█` goes out as `0xDB` and `░` as `0xB0`, their PC437 bytes.
4. Each line, then `LF`. A reversed line sits inside `GS B 1` … `GS B 0`. A double-size line sits inside `GS ! 0x11` … `GS ! 0x00`.
5. `ESC 2`: the default line spacing.

Not yet checked on the MPT-II:

- Code page 0 holds `█` and `░`.
- `ESC 3 24` gives the 24-dot line that the preview draws.
- `GS B` and `GS !` work.
- A full 32-column line may wrap by itself, and the `LF` after it would then print a blank line.
- `FS .` may not be needed.

The design-side checks for text mode are in `design-system/verify.md`, section *Text mode*.

## Add a template

1. Write `web/src/templates/<name>.tsx`. Its default export is `defineTemplate({ … })` (`web/src/templates/define.ts`):
   - `schemaVersion`: starts at 1.
   - `parse`: built from `web/src/templates/validate.ts`.
   - `Component`: renders only the content. `render.html` puts it in `<T.Paper print>`, the 384-dot `#receipt`.
   - `orientation`: `'landscape'` gives a `#receipt` 384 dots tall and as wide as it needs, with the feed at its right end. The pipeline turns it 90° clockwise onto the paper. `sprint` is the example.
   - `lines`: optional text mode. It returns `{ text, double?, reverse? }` lines of printable ASCII plus `█ ░`, at most 32 characters (16 when double). `Component` must preview the same lines with `T.TextMode`. `build` is the example.
2. Helper modules in `web/src/templates/` are `.ts`. Every `.tsx` file there is a template.
3. Write the sample `samples/templates/<name>.json`. `test_every_sample_renders` in `tests/test_ticket_templates.py` renders every sample.
4. Run `make test`.

The `validate.ts` parsers:

| Parser | Accepts |
|---|---|
| `text(max)` | Non-blank text of at most `max` characters. |
| `limitedString(max)` | Text of at most `max` characters. It counts code points, so an emoji is one character. |
| `nonBlank(parser)` | What `parser` accepts, except text that is empty, spaces or zero-width characters. |
| `integer(min, max)` | A whole number from `min` to `max`. |
| `range(min, max)` | A number from `min` to `max`. `-0` becomes `0`. |
| `oneOf(...values)` | One of these strings. |
| `array(item, max, { min })` | A list of `min` to `max` items. |
| `object({ … })` | An object with these fields and no others. |
| `optional(parser)` | The field, or nothing. |

A custom check calls `fail(path, expected)`, or throws `TemplateDataError` with the field path. A template that throws, also inside an effect, fails the render.

Rules for every template:

- Cap every string and list so that the worst case stays under 4000 dots. Add a test that renders the worst case: every list full, every string at its cap, in `W` and in CJK.
- Measure text in the page after `facesLoaded(faces)` (`web/src/templates/faults.ts`) resolves, as `agenda` and `focus` do. Do not model glyph widths: emoji and CJK come from system fonts.
- Refuse blank text that the print shows: use `text` or `nonBlank`. Every template does. A blank value prints an empty field and still reports success.
- Put every edge on a whole pixel.
- Floor a percentage that would otherwise claim a threshold, such as 100% or a quota.

QR codes: `qrMatrix(text)` in `web/src/templates/qr.ts` gives the matrix for `T.QRSlot`. `ticket` draws 3 dots per module. Which module size scans is not yet measured on paper.

## Print locally

```bash
make template PAYLOAD=samples/templates/ticket.json
uv run src/scripts/print_template.py samples/templates/ticket.json --no-print   # PNG only
uv run src/scripts/print_template.py samples/templates/build.json --text        # native text
```

| Flag | Effect |
|---|---|
| `--no-print` | Do not print; only save the output. |
| `--text` | Print native text. The output is `<template>.bin`, the whole job with `ESC @` and the feed, in place of `<template>.png`. |
| `--no-build` | Use the existing `web/dist`; skip `npm run build`. |
| `--artifact-dir DIR` | Save the output in `DIR`, not in `artifacts/template-<utc-timestamp>/`. |

`uv run src/scripts/daily_print.py --template` prints today's and overdue Todoist tasks on the `tasks` template, to compare it with the daily receipt. `src/tasks_template.py` builds the payload, and the run saves it as `tasks.json` in the artifact folder. Without `--template`, `daily_print.py` prints the daily receipt.

To see a design-system component on screen, run `npm run dev` in `web/` and open `/preview.html?c=<Name>`, for example `?c=CellGrid`.

## Design source

`designs/receipt-set-1/` is a verbatim copy of the Claude Design export "Receipt Set 1" (strips 1a to 1n). Open `Receipt Set 1.dc.html` in a browser. Where it and the design system differ, the design system wins.
