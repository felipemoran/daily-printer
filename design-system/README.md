A print system for a 58 mm thermal receipt printer: tickets, PRs, reports, recipes, reminders and memes, all on one 384-dot-wide strip of paper. The paper is the interface: people read it across a desk, tick it with a pen, tear it and tape it up.

## The medium

- **Width is fixed.** 58 mm paper, 48 mm printable, 203 dpi → `paper-width` (384 dots). Design at 1 CSS px = 1 dot. On screen the strip is `strip-width` (448px) with `space-8` margins standing in for the unprintable edge. Wrap every print in `Paper`; render for the printer with `Paper print`, which outputs exactly the 384-dot `#receipt` element.
- **Whole pixels.** Every size, position and line height is a whole number of pixels: line heights are in px, never ratios or `em`; components round bar lengths, column widths and gaps. Fractional positions make Chromium resample images and drift layouts. Avoid centring an odd-height element against an even one (`align-items: center`), which lands it on a half pixel.
- **Length is free.** Receipts can be as long as they need to be, so length can carry meaning (an agenda at 1 h = 56 dots; a banner printed sideways). End every print with `space-feed` so the tear clears the last line.
- **Two values per dot.** The head burns a dot or it doesn't. Pages use `ink`, `paper` and the `tone-*` greys; the print pipeline dithers greys and photos. Never rely on a subtle grey difference.
- **The screen shows structure, paper shows tone.** Prints come out darker than the screen. Judge weight and tone only on paper.
- **Heavy marks smear downward.** The pipeline's erosion compensates; large solids and 900-weight strokes still print heavier and less even than on screen (under test, see To verify).

## Voice and content

- Write like a store receipt: terse, factual, uppercase for labels and states (`IN REVIEW`, `STALE 4D`, `DONE YESTERDAY`), sentence case for titles and comments.
- Lead with the identifier or the number: `OPS-2481`, `99.42%`, `WEEK 40`, `14°`. The hero is what you'd look for from across the room.
- Times are 24-hour `14:08`; dates `01 OCT` or `01.10`; durations `3h 20m`; relative ages `4D`, `6H`.
- Use `·` to join metadata (`planning · due 12:00`), `→` for transitions, `▲ ▼` for change. No emoji: they rasterize into smudges. Plain Unicode glyphs ✓ ◯ █ survive.
- Say what to do, when there is something to do: `→ take a jacket`, `ACK REQUIRED BY 14:07`, `tear & stick`.

## Type

- **Display** (`display-mega` … `display-sm`): Archivo at font-stretch 62%, weight 900. bundle.css applies the stretch on every display class (and `.rp-d`; `.rp-d-wide` for 75% when a word reads too tight, like service names). One display element per section; one hero per receipt.
- **Mono** (`lead`, `item`, `body`, `body-strong`, `label`, `meta`, `meta-strong`, `micro`): IBM Plex Mono. Weight follows size, not role: what matters is stem width in dots, and the target is 2-dot stems (1 dot prints faint, 3–4 too bold). The current weights are provisional until measured (see To verify).
- **Floor:** 16px for any running text, 14px only in bold for axis ticks (`micro`); unverified.
- **Reverse:** text on `ink` is set 700; unverified.
- **Text on tones:** never. Text sits on `paper` or `ink`; over a tone it goes on a paper plate.
- **Text mode** (`textmode`, `textmode-double`): `TextMode` previews a print sent as native ESC/POS text in the printer's Font A (12 × 24-dot cell, 32 columns; double size 16 columns). JetBrains Mono only stands in on screen; the real output is text, never a raster. Font A is the best type the printer has, and native text is the only output that prints over Bluetooth.
- All three faces are hosted on Google Fonts; load them before rasterizing.

## Strokes and layout

- Strokes come from `stroke-*` (erosion may print horizontal rules of 3px and up a dot thinner; under test): `stroke-hair` 2px dashed between list items and as leaders; `stroke-rule` 3px between sections; `stroke-box` 4px for tile grids, checkboxes, chart baselines; `stroke-heavy` 6px for the one `Callout`; `stroke-bar` 8px only under the `Masthead`. Never 1px.
- Corners are square (`radius-none`). Curves stair-step at 203 dpi; keep them inside type.
- Stack on the spacing scale: `space-3` between rows inside a section, `space-6`–`space-7` between sections.
- Hierarchy is weight and scale, not colour: masthead → bar rule → section labels → rows separated by hair rules.

## Tones

Greys are real greys; the print pipeline dithers them. The values are provisional until printed (TestTones).

| Token | Grey | Use |
| --- | --- | --- |
| `ink` | 100% | current value, done, down, the state that matters |
| `tone-65` | 65% | degraded cells, removed lines |
| `tone-50` | 50% | previous period, focus blocks, below-target bars |
| `tone-35` | 35% | skipped days, secondary marks |
| `tone-15` | 15% | quiet backgrounds, QR placeholder |

- A chart has at most three states: hollow, a tone, solid. Give tone areas a `stroke-hair` outline so their edge stays crisp.
- Text never sits on a tone. Always print the number too: the tone is a glance, the value is the record.
- `HazardTape` stays a black-and-white stripe pattern: it is a graphic, not a shade.

## Building a print

Every print is `Paper` → a head (`Masthead` for scheduled prints, `HeaderBar` + display ID for event prints) → sections opened by `SectionLabel` or a `Rule` → at most one `Callout` → optional `TearLine` stub → feed.

| Print | Template | Built from |
| --- | --- | --- |
| Ticket / issue update | `TicketTemplate` | HeaderBar, display-xl ID, Transition, Leaders, Quote, QRSlot |
| PR review queue | `PullRequestTemplate` | display title, Tag, DiffGlyph |
| Incident / alarm | `IncidentTemplate` | HazardTape, Severity, LogList, Callout |
| Data report | `ReportTemplate` | Masthead, StatTiles, BarList, Columns |
| Uptime, habits, calendars | — | CellGrid |
| Daily tasks | `TasksTemplate` | Masthead, TaskRow, StatTiles |
| Recipe | `RecipeTemplate` | HeaderBar, TaskRow (ingredients), Step, NoteLines, TearLine |
| Reminder / focus ticket | `ReminderTemplate` | display text, BoxRow, NoteLines |
| Meme / photo | `MemeTemplate` | display captions, Image |
| CI / cron output | — | TextMode |

Patterns from the explorations that are layouts, not components:

- **Agenda to scale:** hour lines as `stroke-hair` dashed rules every 56 dots; meetings as `stroke-rule` hollow boxes, focus blocks `tone-50`, the current event reversed, a 6px NOW line.
- **Banner mode:** rotate the raster 90° and the strip becomes a 384-dot-tall banner of any length, for wide layouts like a kanban board. Column heads take `stroke-heavy` underlines; cards `stroke-rule` boxes.
- **Morning briefing:** `GOOD MORNING` label between two `Rule weight="double"`, the day in `display-xl`, weather as a `display-hero` figure, a 3-up `StatTiles` of counts, then `Callout` THE ONE THING.

## Pen and paper

Prints invite a pen: hollow `Checkbox`es, `BoxRow` for counting, `NoteLines` for notes, `done at ______ ◯ ◯ ◯` on stubs. Leave the hollow state hollow; never pre-fill what a person is meant to mark.

## Imagery and iconography

- No icon set. Glyphs that survive: ✓ → ▲ ▼ ◯ █ “. Draw anything else from boxes and tones.
- Photos and memes go in `Image` at full `paper-width` on whole pixels; the pipeline handles dithering and tone. Captions sit above or below, never on the picture.
- QR codes go in `QRSlot` as a module matrix drawn on whole dots. The module size is untested (TestQR prints 1–5 dots per module).
- There is no logo; the system's name is set in plain display type.

## Screen-only tokens

`canvas`, `canvas-ink` and `canvas-muted` paint the desk around the strip in previews and docs. They are never sent to the printer; `Paper print` leaves them out.

## Tests

The `Tests` group holds print-mode strips for the open questions in To verify: `TestStrokes`, `TestTones`, `TestQR`, `TestType`, `TestSolids`. Print them through the pipeline as they are; each one's guidelines say what to look for.
