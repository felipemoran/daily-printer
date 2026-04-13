# Agent & Contributor Instructions

This file documents the conventions for this repo.
It applies to all contributors — human, AI agent, or otherwise.
Follow all conventions below without being asked.

> Claude Code: this file is referenced from `CLAUDE.md` and loaded automatically.

---

## Version Control: Jujutsu (jj)

This repo is managed with **jujutsu (`jj`)**, not plain git.
All changes to the working directory are automatically tracked in the current commit.

### Rules

1. **Start every new task with a new commit:**
   ```
   jj new -m "<short description>"
   ```
   A "task" means a new feature, fix, planning document, or any logical unit of work.
   Do this *before* making changes, so the description matches the content from the start.

2. **Update the description if the work shifts:**
   If what you ended up implementing differs from the initial message, update it:
   ```
   jj describe -m "<revised description>"
   ```

3. **Keep commits small and focused:**
   One logical change per commit. Do not batch unrelated edits.

4. **Never use `git commit` directly.**
   jj manages the git backend. Use `jj` commands only.

5. **Check status before starting:**
   ```
   jj status
   jj log
   ```

---

## Project Layout

```
daily-printer/
├── AGENTS.md          ← you are here
├── CLAUDE.md          ← stub, points here (for Claude Code auto-detection)
├── docs/              ← all documentation
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
| Print width | 48 mm / ~384 dots at 203 DPI |
| Library | `python-escpos` (v3.1+) |
