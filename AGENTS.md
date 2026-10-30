# Agent & Contributor Instructions

This file documents the conventions for this repo.
It applies to all contributors — human, AI agent, or otherwise.
Follow all conventions below without being asked.

> Claude Code: this file is referenced from `CLAUDE.md` and loaded automatically.

---

## Pending work lives in bacon

The operator works on this project in small increments and picks it up later from tasks, not from old chat. A pending item that exists only in a reply is lost.

- Capture every pending item as a bacon task in `tasks/`, in the same turn that surfaces it. This covers a deferred fix, a follow-up, an open question or decision, an action only the operator can take, a step you skipped or did not verify, and work you offered but did not start.
- Use the status that says who moves next: `operator` when it waits on the operator (write the question or the action in the task), `draft` for a follow-up nobody committed to, `pending` for work ready to pick up.
- When a pending item changes, update its task in the same turn: `done` when it is finished, `skipped` with a recorded decision (`bacon decide`) when it is dropped.
- In a reply, put the task id next to each pending item.
- Task changes reach `main` on a branch and through a PR, like any change. Ask the operator before you open a PR that holds only tasks.
- After a PR merges, never add a commit to it. Put a late task update in the first commit of the next branch.

---

## Version Control: Jujutsu (jj)

This repo is managed with **jujutsu (`jj`)**, not plain git.

**Not git:** filesystem edits belong to the working-copy revision (**`@`**) immediately — there is no index/stage step. For each slice, **`jj new -m "…"` first, then edit** (see rule 1 for the empty-`@` exception). When the slice is done, **`jj new -m "<next>"`** to stack the next change on top; the slice you leave behind already has the description from when you opened it. Use **`jj describe -m`** only when the work outgrew that message (rule 2). Do **not** use **`jj commit`**.

### Rules

1. **Start every new task with a new commit:**
   ```
   jj new -m "<short description>"
   ```
   A "task" means a new feature, fix, planning document, or any logical unit of work.
   Do this *before* making changes, so the description matches the content from the start.

   **Exception — reuse an empty, undescribed commit:** Before creating a new commit,
   check `jj status`. If the current commit is empty and has no description, set its
   description instead of creating a new one:
   ```
   jj describe -m "<short description>"
   ```
   If the current commit already has content or a description, always create a new one.

2. **Update the description if the work shifts:**
   If what you ended up implementing differs from the initial message, update it:
   ```
   jj describe -m "<revised description>"
   ```

3. **Keep commits small and focused:**
   One logical change per commit. Do not batch unrelated edits.

   **Long features:** Use a **new `jj` commit for each coherent step** (`jj new -m "<step>"`)
   instead of accumulating an entire feature in one change set. Split implementation into
   reviewable slices (for example: scaffolding, core behavior, wiring, tests, or docs) so no
   single commit mixes too many files or concerns.

4. **Never use `git commit` or `jj commit`.**
   jj manages the git backend; use **`jj new`** / **`jj describe`** as above, not `jj commit`.

5. **Check status before starting:**
   ```
   jj status
   jj log
   ```

6. **Use `--tool :git` when diffing file contents:**
   ```
   jj diff --tool :git
   jj diff --tool :git -r <rev>
   ```
   Without this flag, `jj diff` uses its default formatter which may not show content
   correctly. Always pass `--tool :git` when you need to inspect actual file changes.

---

## Project Layout

```
daily-printer/
├── AGENTS.md          ← you are here
├── CLAUDE.md          ← stub, points here (for Claude Code auto-detection)
├── docs/              ← all documentation (`README.md` = index)
│   └── <phase-or-scope>-<topic>.md
├── src/               ← all Python source code
├── pyproject.toml     ← uv project config
└── .venv/             ← managed by uv, do not touch directly
```

### Naming docs

Doc filenames must indicate both **scope** (planning phase, feature name, etc.) and **topic**:

```
docs/planning-phase-01-printer-research.md
docs/feature-daily-brief-layout.md
docs/setup-usb-macos-troubleshooting.md
```

---

## Python Tooling: uv

- Add dependencies: `uv add <package>`
- Run scripts:      `uv run src/<script>.py`
- Never use `pip` directly.

---

## Printer Quick Reference

| Field | Value |
|---|---|
| USB Vendor ID | `0x6868` |
| USB Product ID | `0x0200` |
| Protocol | ESC/POS |
| Print width | 48 mm / **384 dots** at 203 DPI (confirmed by calibration) |
| Library | `python-escpos` (v3.1+) + `bleak` (BLE) |
| BLE TX char | `49535343-8841-43f4-a8d4-ecbe34729bb3` (MLDP) |
| Images | USB cable only: BLE garbles rasters (`docs/setup-bluetooth-investigation.md`) |
| Print settings | `src/print_profile.py`; why: `docs/research-print-quality.md` |
| Design system | `design-system/` mirrors Claude Design; never edit it by hand (`docs/feature-design-system.md`) |
| Print templates | `web/src/templates/`, one `.tsx` per template; rendered by `src/ticket_templates.py` (`docs/feature-ticket-templates.md`) |
