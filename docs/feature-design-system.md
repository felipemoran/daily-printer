# Feature: Thermal design system

Thermal is the design system for prints. Its source of truth is the Claude Design artifact <https://claude.ai/artifact/15ynCEqRKpQdbxXuvZw3nr> (private). Change the design there, then sync it into the repo.

## Where things are

| Path | What |
|---|---|
| `design-system/` | Verbatim mirror of the artifact's `project/` folder. Never edit it by hand: the next sync overwrites it. Start with its `README.md` (the rules) and `verify.md` (the open paper checks). |
| `web/src/thermal/index.ts` | Runs the mirrored `bundle.js` and exports its components, typed: `import T from './thermal'`. |
| `web/src/thermal/generated/` | Written by the sync script: `tokens.css` (variables and type classes from `tokens.json`), `bundle.css` (without the Google Fonts import) and `thermal.d.ts` (component props). |
| `web/public/fonts/` | Self-hosted Archivo, IBM Plex Mono and JetBrains Mono, so renders work offline. Declared in `web/src/fonts.css`. |
| `web/thermal.html` | Example page: `TicketTemplate` ported from the artifact. |
| `web/preview.html` | Runs any mirrored `preview.html` unchanged: `preview.html?c=<Component>`. |

## Sync from Claude Design

1. Ask Claude Code to download every `project/` file of the artifact into a folder. Its Artifact tool saves each file at `<folder>/project/<path>`.
2. Run `make design-sync SRC=<folder>/project`. It replaces `design-system/` and regenerates `web/src/thermal/generated/`.
3. Run `make test`, then read the diff of `design-system/` before you commit.

The sync stops with an error when the artifact has more than one colour theme, lists font files in `tokens.json`, or renames the bundle's `Thermal` namespace. Each one needs a code change here first.

`tests/test_design_system.py` fails when the generated files no longer match the mirror. Fix: `make design-sync` without `SRC`.

## Print a preview as is

`web/preview.html?c=<Component>` runs that component's preview script from `design-system/` without a port. It prints only previews that use `<Paper print>`: today, the `Test*` strips.

```bash
cd web && npm run build
uv run src/scripts/page_print.py --page "web/dist/preview.html?c=TestTones"
```

The strips answer the open checks in `design-system/verify.md`; each strip's `README.md` says what to look for. Settle the results in Claude Design, then sync.

## Port a design

A component preview in the artifact is React without JSX. Port it line by line:

| Artifact preview | Repo |
|---|---|
| `h(T.Paper, null, …)` | `<T.Paper print>…</T.Paper>` |
| `h(T.Leaders, { rows: […] })` | `<T.Leaders rows={[…]} />` |
| `h('div', { className: 'display-xl', style: {…} }, 'OPS-2481')` | `<div className="display-xl" style={{…}}>OPS-2481</div>` |

Keep class names and inline styles as they are. `print` makes `Paper` render the bare 384-dot `#receipt` that the pipeline captures; previews in the artifact leave it out to show the strip on a desk.

## Print

```bash
cd web && npm run build
uv run src/scripts/page_print.py --page web/dist/thermal.html --no-print
```

Every other step of the print profile applies, with one exception: automatic weight skips pages whose `#receipt` has the `rp-paper` class, so the design system's own weights reach the paper.

Glyphs outside the Latin subsets (`→ ▲ ✓ █`) fall back to a system font.
