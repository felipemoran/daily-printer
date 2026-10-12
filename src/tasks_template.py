"""Map Todoist's TaskSections onto the `tasks` template (web/src/templates/tasks.tsx)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from todoist_api_python.models import Task

from task_formatter import _strip_markdown_links
from todoist_client import TaskSections

# Mirror the caps in web/src/templates/tasks.tsx. Its limitedString counts UTF-16 code units.
TASKS_MAX = 30
TITLE_MAX = 160
META_MAX = 80

# Todoist's API numbers priority backwards: 4 is the app's P1. P4 is the default and gets no tag.
_PRIORITY_TAGS = {4: "P1", 3: "P2", 2: "P3"}


def _units(char: str) -> int:
    return 2 if ord(char) > 0xFFFF else 1


def _clip(text: str, limit: int) -> str:
    if sum(map(_units, text)) <= limit:
        return text
    kept, used = [], 0
    for char in text:
        if used + _units(char) > limit - 1:
            break
        kept.append(char)
        used += _units(char)
    return "".join(kept) + "…"


def _due_date(task: Task) -> date | None:
    if task.due is None:
        return None
    due = task.due.date
    return due.astimezone().date() if isinstance(due, datetime) else due


def _row(task: Task, today: date | None) -> dict[str, Any]:
    """``today`` is set for an overdue task, to print its age."""
    parts: list[str] = []
    if today is not None:
        due = _due_date(task)
        parts.append(f"OVERDUE {(today - due).days}D" if due else "OVERDUE")
    elif task.due is not None and isinstance(task.due.date, datetime):
        parts.append(task.due.date.astimezone().strftime("%H:%M"))
    parts += task.labels or []
    row: dict[str, Any] = {"title": _clip(_strip_markdown_links(task.content), TITLE_MAX)}
    if parts:
        row["meta"] = _clip(" · ".join(parts), META_MAX)
    if task.priority in _PRIORITY_TAGS:
        row["priority"] = _PRIORITY_TAGS[task.priority]
    return row


def tasks_payload(sections: TaskSections, now: datetime) -> dict[str, Any]:
    """Today's and overdue tasks; upcoming tasks are not today's list."""
    rows = [_row(task, None) for task in sections.today]
    rows += [_row(task, now.date()) for task in sections.overdue]
    data: dict[str, Any] = {
        "weekday": now.strftime("%a").upper(),
        "date": now.strftime("%d %b").upper(),
        "year": now.strftime("%Y"),
        "tasks": rows[:TASKS_MAX],
        "printedAt": now.strftime("%H:%M"),
    }
    if len(rows) > TASKS_MAX:
        data["more"] = len(rows) - TASKS_MAX
    return {"template": "tasks", "schemaVersion": 1, "data": data}
