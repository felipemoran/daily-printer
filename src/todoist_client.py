"""
Thin wrapper around the Todoist REST API SDK.

Fetches tasks grouped into three sections:
  - today:    due today (not overdue)
  - overdue:  past due, oldest first
  - upcoming: due tomorrow or the day after, sorted soonest first

Usage:
    from todoist_client import get_task_sections
    sections = get_task_sections(token)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task


@dataclass
class TaskSections:
    today: list[Task] = field(default_factory=list)
    overdue: list[Task] = field(default_factory=list)
    upcoming: list[Task] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _token_from_env() -> str:
    token = os.environ.get("TODOIST_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TODOIST_API_TOKEN is not set. "
            "Export it in your shell or add it to a .env file."
        )
    return token


def _exclude_subtasks(tasks: list[Task]) -> list[Task]:
    return [t for t in tasks if t.parent_id is None]


def _sort_by_due(tasks: list[Task], reverse: bool = False) -> list[Task]:
    """Sort tasks by due date/datetime, placing tasks without a due date last."""
    from datetime import date, datetime as dt

    _max = dt(9999, 12, 31, 23, 59, 59)

    def sort_key(t: Task):
        if t.due is None:
            return _max
        d = t.due.date  # datetime.date or datetime.datetime in SDK v4
        if isinstance(d, dt):
            return d
        if isinstance(d, date):
            return dt(d.year, d.month, d.day)
        return _max

    return sorted(tasks, key=sort_key, reverse=reverse)


def get_task_sections(token: str | None = None) -> TaskSections:
    """
    Fetch tasks from Todoist and return them grouped into sections.

    Args:
        token: Todoist API token. If None, reads from TODOIST_API_TOKEN env var.

    Returns:
        TaskSections with today, overdue, and upcoming lists.
    """
    if token is None:
        token = _token_from_env()

    api = TodoistAPI(token)

    def _fetch(query: str) -> list[Task]:
        # filter_tasks returns a ResultsPaginator that yields pages (list[Task])
        return [task for page in api.filter_tasks(query=query) for task in page]

    # Three independent fetches — one per section, using Todoist's own filter engine.
    raw_today = _fetch("today")
    raw_overdue = _fetch("overdue")
    # Tomorrow + day after: "in 3 days" is exclusive upper bound in Todoist syntax
    raw_upcoming = _fetch("due after: today & due before: in 3 days")

    today = _sort_by_due(_exclude_subtasks(raw_today))
    overdue = _sort_by_due(_exclude_subtasks(raw_overdue))  # oldest first (default asc)
    upcoming = _sort_by_due(_exclude_subtasks(raw_upcoming))

    return TaskSections(
        today=today,
        overdue=overdue,
        upcoming=upcoming,
    )
