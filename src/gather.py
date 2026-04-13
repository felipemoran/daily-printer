"""
Generic data-gather step for the daily receipt.

Each source is a function that returns a list of blocks (dicts matching
the Block union in web/src/receiptPayload.ts, schemaVersion 2).

To add a new source later:
  1. Write a function that returns list[dict] of blocks.
  2. Append a call to it in gather().

The gather() function returns a ready-to-serialize payload dict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

Block = dict[str, Any]
Payload = dict[str, Any]

SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def _gather_todoist() -> list[Block]:
    from task_formatter import sections_to_payload
    from todoist_client import get_task_sections

    sections = get_task_sections()
    payload = sections_to_payload(sections)
    return payload["blocks"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather() -> Payload:
    """
    Fetch all data sources and return a schemaVersion-2 payload dict.

    Extend by adding more _gather_*() calls below.
    """
    blocks: list[Block] = []

    blocks.extend(_gather_todoist())
    # blocks.extend(_gather_weather())
    # blocks.extend(_gather_emails())

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "blocks": blocks,
    }
