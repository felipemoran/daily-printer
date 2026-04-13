# Feature: Todoist Task Integration

## Research Summary

### API & SDK

- **REST API**: Todoist REST API v2 (`https://api.todoist.com/rest/v2/`)
- **Python SDK**: [`todoist-api-python`](https://github.com/Doist/todoist-api-python) (official, by Doist)
  - Current: v4.x (uses `httpx` internally, breaking change from v3)
  - Install: `uv add todoist-api-python`
- **Auth**: Bearer token — personal API token from Todoist → Settings → Integrations
  - Store as env var `TODOIST_API_TOKEN`

### Key SDK Methods

```python
from todoist_api_python.api import TodoistAPI

api = TodoistAPI(token)

# General task fetch with filters
tasks = api.filter_tasks(query="today")          # returns Iterator[list[Task]]

# Task model fields we use:
# task.content        — task title
# task.due            — Due object or None
#   task.due.date     — "YYYY-MM-DD" string (date-only tasks)
#   task.due.datetime — ISO 8601 string (time-specific tasks), may be None
#   task.due.string   — human-readable string from Todoist
# task.labels         — list[str] of label names
# task.parent_id      — str or None (non-None = subtask)
```

### Filter Syntax

Todoist filter queries passed to `filter_tasks(query=...)`:

| Section | Filter Query |
|---|---|
| Today | `"today"` |
| Overdue | `"overdue"` |
| Upcoming (3 days after today) | `"due after: today & due before: in 4 days"` |

Notes:
- `overdue` does NOT include today; `today` does NOT include overdue — sections are mutually exclusive.
- Subtasks are excluded client-side by checking `task.parent_id is not None`.

---

## Design

### Authentication

```
TODOIST_API_TOKEN=<token>  # set in shell or .env file (not committed)
```

A helper reads it from the environment and raises a clear error if missing.

### Data Flow

```
TodoistAPI (SDK)
    └── filter_tasks(query) × 3  →  raw Task lists
            └── task_sections.py
                    ├── today_tasks     — due today, sorted by due time (asc)
                    ├── overdue_tasks   — overdue, sorted by due date (oldest first)
                    └── upcoming_tasks  — due in next 3 days after today, grouped by day
                            └── renderers (text / HTML / ESC-POS)
```

### Module: `src/todoist_client.py`

Thin wrapper around the SDK:

```python
def get_task_sections(token: str) -> TaskSections:
    """Fetch and return tasks grouped into today/overdue/upcoming."""
```

Returns a `TaskSections` dataclass:
```python
@dataclass
class TaskSections:
    today: list[Task]
    overdue: list[Task]       # sorted: oldest due date first
    upcoming: list[Task]      # sorted: soonest first; 3 days after today
    fetched_at: datetime
```

Three separate `filter_tasks` calls (one per section) — keeps logic simple and avoids client-side date math beyond what's necessary.

### Upcoming Day Range

- Day 1 = today (already in `today` section)
- Upcoming = tasks due on days 2–4 (tomorrow through 3 days from now)
- Filter: `"due after: today & due before: in 4 days"`

> **Open assumption**: if you meant a today-inclusive 3-day window (tomorrow + day+2 only), change the filter to `"due before: in 3 days & due after: today"`.

---

## Print Layout

### Section Structure

```
━━━━━━━━━━━━━━━━━━━━━━━━
  TODAY — Mon Apr 13
━━━━━━━━━━━━━━━━━━━━━━━━

[ ] Buy groceries
    [no time]  •  errands, personal

[ ] Call dentist
    2:30 PM  •  health

━━━━━━━━━━━━━━━━━━━━━━━━
  OVERDUE (3)
━━━━━━━━━━━━━━━━━━━━━━━━

[ ] File taxes
    Apr 1  •  5 days ago  •  finance

[ ] Review contract
    Apr 10  •  yesterday  •  work

━━━━━━━━━━━━━━━━━━━━━━━━
  UPCOMING
━━━━━━━━━━━━━━━━━━━━━━━━

Tue Apr 14
  [ ] Team standup notes  •  work

Wed Apr 15
  [ ] Renew gym membership  •  health, finance

Thu Apr 16
  [ ] Dentist appointment  •  health
```

### Per-Task Format

Line 1: `<title>`
Line 2: `<due date>  •  <elapsed/countdown>  •  <labels>`

- **Elapsed / countdown**:
  - Overdue: `N days ago` / `yesterday`
  - Upcoming: `tomorrow` / `in N days`
- **Labels**: comma-separated; omit line if no labels and no useful time info

### Width Budget (384 dots = ~32 chars at default font)

> Exact character count depends on ESC/POS font mode. At font A (12×24), 384 dots ÷ 12 = **32 chars**. At condensed / font B (8×16), ~48 chars. Default to 32-char wrap.

Long titles wrap to 2 lines max; line 2 data wraps to 2 lines max.

---

## Implementation Plan

1. `uv add todoist-api-python python-dotenv`
2. `src/todoist_client.py` — API wrapper, returns structured tasks (or similar)
3. `src/task_formatter.py` — formats tasks into the **receipt JSON** shape (`samples/receipt-sample.json`, `web/src/receiptPayload.ts`)
4. Gather step writes **`payload.json`**; run **`src/scripts/receipt_print.py`** (see **`docs/feature-receipt-print-cli.md`**) to render, capture, and print
