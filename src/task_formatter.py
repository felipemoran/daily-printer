"""
Converts a TaskSections object into a receipt payload v2 JSON file.

The output schema matches web/src/receiptPayload.ts (schemaVersion 2).

Usage:
    from task_formatter import sections_to_payload, write_payload
    payload = sections_to_payload(sections)
    write_payload(payload, "payload.json")

Or from the CLI:
    uv run src/task_formatter.py            # writes payload.json
    uv run src/task_formatter.py out.json   # custom path
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from todoist_api_python.models import Task

from todoist_client import TaskSections, get_task_sections


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------

_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_due_date(task: Task) -> date | None:
    if task.due is None:
        return None
    raw = task.due.datetime or task.due.date
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_due_time(task: Task) -> str | None:
    """Return formatted time string like '2:30 PM' if task has a specific time."""
    if task.due is None or not task.due.datetime:
        return None
    try:
        dt = datetime.fromisoformat(task.due.datetime.replace("Z", "+00:00"))
        # Convert to local time for display
        local = dt.astimezone()
        hour = local.hour
        minute = local.minute
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        if minute:
            return f"{display_hour}:{minute:02d} {period}"
        return f"{display_hour} {period}"
    except ValueError:
        return None


def _format_date_short(d: date) -> str:
    """Format as 'Apr 1'."""
    return f"{_MONTH_ABBR[d.month]} {d.day}"


def _format_date_label(d: date) -> str:
    """Format as 'Tue Apr 14'."""
    return f"{_DAY_ABBR[d.weekday()]} {_MONTH_ABBR[d.month]} {d.day}"


def _relative_overdue(d: date, today: date) -> str:
    delta = (today - d).days
    if delta == 1:
        return "yesterday"
    return f"{delta} days ago"


def _relative_upcoming(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 1:
        return "tomorrow"
    return f"in {delta} days"


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------

Block = dict[str, Any]


def _task_block(task: Task, time: str | None = None, relative: str | None = None) -> Block:
    block: Block = {"type": "task", "content": task.content}
    if time:
        block["time"] = time
    if relative:
        block["relative"] = relative
    if task.labels:
        block["labels"] = list(task.labels)
    return block


def _build_today_blocks(tasks: list[Task]) -> list[Block]:
    if not tasks:
        return []
    today = _today()
    label = f"TODAY — {_DAY_ABBR[today.weekday()]} {_MONTH_ABBR[today.month]} {today.day}"
    blocks: list[Block] = [{"type": "section_header", "title": label}]
    for task in tasks:
        blocks.append(_task_block(task, time=_parse_due_time(task)))
    return blocks


def _build_overdue_blocks(tasks: list[Task]) -> list[Block]:
    if not tasks:
        return []
    today = _today()
    blocks: list[Block] = [
        {"type": "section_header", "title": "OVERDUE", "count": len(tasks)}
    ]
    for task in tasks:
        due = _parse_due_date(task)
        time_str = _format_date_short(due) if due else None
        relative = _relative_overdue(due, today) if due else None
        blocks.append(_task_block(task, time=time_str, relative=relative))
    return blocks


def _build_upcoming_blocks(tasks: list[Task]) -> list[Block]:
    if not tasks:
        return []
    today = _today()

    # Group by due date
    by_day: dict[date, list[Task]] = {}
    for task in tasks:
        due = _parse_due_date(task)
        if due is None:
            continue
        by_day.setdefault(due, []).append(task)

    if not by_day:
        return []

    blocks: list[Block] = [{"type": "section_header", "title": "UPCOMING"}]
    for day in sorted(by_day):
        blocks.append({"type": "day_header", "title": _format_date_label(day)})
        relative = _relative_upcoming(day, today)
        for task in by_day[day]:
            blocks.append(_task_block(task, time=_parse_due_time(task), relative=relative))
    return blocks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sections_to_payload(sections: TaskSections) -> dict[str, Any]:
    """Convert TaskSections to a schemaVersion-2 payload dict."""
    blocks: list[Block] = []
    blocks.extend(_build_today_blocks(sections.today))
    blocks.extend(_build_overdue_blocks(sections.overdue))
    blocks.extend(_build_upcoming_blocks(sections.upcoming))

    return {
        "schemaVersion": 2,
        "generatedAt": sections.fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "blocks": blocks,
    }


def write_payload(payload: dict[str, Any], path: str | Path = "payload.json") -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    out_path = sys.argv[1] if len(sys.argv) > 1 else "payload.json"

    print("Fetching tasks from Todoist…", flush=True)
    sections = get_task_sections()
    today_count = len(sections.today)
    overdue_count = len(sections.overdue)
    upcoming_count = len(sections.upcoming)
    print(
        f"  today={today_count}  overdue={overdue_count}  upcoming={upcoming_count}",
        flush=True,
    )

    payload = sections_to_payload(sections)
    write_payload(payload, out_path)
    print(f"Written → {out_path}", flush=True)
