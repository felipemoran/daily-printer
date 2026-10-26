# Hand-off: mise-en-place prints (both repos)

Written 2026-10-25 by the session that built and landed the print system. This file is committed on a local branch; delete it before that branch's PR merges.

## Goal

Print two things from mise-en-place on the receipt printer, end to end, with both repos kept in sync:

1. the shopping list (task `1z19qx`, "Template: shopping list from mise-en-place");
2. a recipe with its ingredient amounts and steps (task `vsz7c3`, "Template: recipe with amounts from mise-en-place").

Operator decision (recorded with `bacon decide` in both tasks): mise-en-place gets a Print button; the site sends the data in a REST request; the print system prints it. The print server does not read mise-en-place's data or its week state.

## Done (state you inherit)

- daily-printer `main` holds the print system and 14 ticket templates (PRs 1 and 2 merged 2026-10-25). The REST intake already exists: `POST /api/jobs` with `kind: "template"` and a payload `{template, schemaVersion, data}`. The template contract and "Add a template" steps are in `docs/feature-ticket-templates.md`; the API and auth are in `docs/planning-print-system-architecture.md` (section "Interfaces").
- PR 3 (https://github.com/felipemoran/daily-printer/pull/3, draft, branch `felipe/docker-compose`) adds Docker Compose and, in its first commit (`kqtqww`), the task files for all follow-up work, including `1z19qx` and `vsz7c3` with the decision above. Reviewed twice; not merged yet.
- In mise-en-place nothing was changed. Only read: `README.md`, `worker/index.js`, `functions/_middleware.js`, `worker/wrangler.toml`.

## Environment

- daily-printer workspace: `/Users/felipemoran/projects/daily-printer/.workspaces/mise-print__daily-printer`. Its `@` (this file's commit, "chore: handoff") sits on `felipe/docker-compose` (PR 3's tip, change `xqvwkr`), so the two task files are present.
- **Do not open a PR from this workspace until PR 3 merges.** A PR based on `felipe/docker-compose` would be stacked. After PR 3 merges (`jj git fetch`), rebase this work onto `main@origin` (if PR 3 is squash-merged: `jj rebase -s 'roots(felipe/docker-compose..@)' -d main@origin`; if merged with a merge commit, as PR 1 and 2 were, no rebase is needed), then push and open the draft PR.
- mise-en-place repo: `/Users/felipemoran/projects/mise-en-place` (jj, has `.workspaces/` and its own bacon `tasks/`). Create a dedicated workspace there with `jworkspace-create --name print-button --no-claude --no-code`; never edit its `default` workspace.
- Print server locally: `make demo` in a daily-printer workspace (admin at http://127.0.0.1:8787/admin, admin token `moranlindo`, demo only), or `make compose-test` on PR 3's branch.
- Docker on this Mac: `~/.docker/config.json` sets `credsStore: desktop`, so each docker call triggers a macOS "access data from other apps" prompt that the operator dislikes. Run docker with a temporary `DOCKER_CONFIG` folder that has no `credsStore`, a copy of `~/.docker/contexts/` and a link to `~/.docker/cli-plugins`. Never edit the operator's docker config.

## Pending (in order)

1. **mise-en-place tasks.** File matching bacon tasks in mise-en-place for the Print button (shopping list, recipe card), linking the daily-printer task ids. Ask the operator first if unsure whether they want tasks in both repos.
2. **Settle the open decisions below with the operator.** The auth decision changes both sides.
3. **Payload contract.** Define the two template payloads from mise-en-place's real data: `dados/esquemas/receita.schema.json`, `dados/receitas/<id>.json`, and what the site's "Semana" and "Lista de compras" views compute (portions scaling, aisles from `dados/secoes.json`, book recipes with `componentes`). Write the contract once (daily-printer template docs) and point to it from mise-en-place.
4. **daily-printer:** build the `shopping-list` and `recipe` templates (sample payloads in `samples/templates/`, tests, docs), following "Add a template". Long recipes must respect the 50 cm print limit (decide: refuse, or split).
5. **mise-en-place:** the Print button on the shopping list and on a recipe card, building the payload from what the page shows; tests in its `tests/`.
6. **End to end:** the site (local) → print server (`make demo`) → fake printer; then review, gates, and one draft PR per repo (the daily-printer one only after PR 3 merges).

## Open decisions (operator's)

- **How the site reaches the print server and authenticates.** A client token in a public static site is readable by anyone. Lean: a `POST /print` route in mise-en-place's existing Worker (`worker/index.js`, which already relays every request with a shared secret) holds the print-server client token as a Worker secret and forwards to the print server's sender hostname. That hostname is behind Cloudflare Access, so the Worker would also need an Access service token. Alternatives: an Access login on the button itself; or a print-server route for this one client.
- **Which printer** the button targets (fixed per deployment, or chosen on the page).
- **Shopping list content:** print ticked items or not; include the pantry ("Despensa", no quantities) or not.
- **Recipe content:** steps only from cook mode, or the card's full text; the portions shown at print time.
- **Long recipes past 50 cm:** refuse with a clear error, or split into two prints.

## Verified vs inherited

- Verified this session: PRs 1 and 2 merged (`gh pr view`); PR 3 open as a draft with two clean review rounds and `make compose-test` passing; the two task files exist on PR 3's branch; mise-en-place's Worker relays with a shared secret (read its code).
- Inherited, not checked: the mise-en-place README's description of the data and the build (`componentes`, `densidade`, `quantidades`); whether the deployed print server is reachable from Cloudflare (it is not deployed yet: task `j2rw5f`); the design system's RecipeTemplate preview as a layout starting point.

## Suggested skills

- `jj-workflow` (both repos use jj), `bacon` (task records in both repos), `review` (independent review before each PR), `reconcile-strays` (before review, if you run builders in parallel).
