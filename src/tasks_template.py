"""Map gather()'s receipt payload onto the `tasks` template (web/src/templates/tasks.tsx)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Mirrors the limitedString caps in web/src/templates/tasks.tsx.
TITLE_MAX = 160
META_MAX = 80


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _time_24h(text: str) -> str:
    for pattern in ("%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(text, pattern).strftime("%H:%M")
        except ValueError:
            pass
    return text


def tasks_payload(receipt: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Today's and overdue tasks from ``receipt``; upcoming tasks are not today's list."""
    tasks: list[dict[str, Any]] = []
    section = ""
    for block in receipt.get("blocks", []):
        if block["type"] == "section_header":
            section = block["title"].split()[0]
        elif block["type"] == "task" and section in ("TODAY", "OVERDUE"):
            if section == "TODAY":
                parts = [_time_24h(block["time"])] if "time" in block else []
            else:
                parts = ["overdue", block["relative"]] if "relative" in block else ["overdue"]
            parts += block.get("labels", [])
            task: dict[str, Any] = {"title": _clip(block["content"], TITLE_MAX)}
            if parts:
                task["meta"] = _clip(" · ".join(parts), META_MAX)
            tasks.append(task)
    return {
        "template": "tasks",
        "schemaVersion": 1,
        "data": {
            "weekday": now.strftime("%a").upper(),
            "date": now.strftime("%d %b").upper(),
            "year": now.strftime("%Y"),
            "tasks": tasks,
            "printedAt": now.strftime("%H:%M"),
        },
    }
