"""Notion-ready payload renderer (MKT-4E).

Pure function. **Does NOT hit the Notion API.** Returns a dict that
mirrors the shape Notion's ``databases.create`` + ``pages.create``
endpoints expect, so a downstream sync tool can consume it without
re-mapping fields.

The payload has two top-level keys:

- ``database`` — properties schema for the Notion database (Name,
  Status, Priority, Category, Channel, Asset Kind, Asset Ref, Due
  Date, Depends On, Owner Hint, Description).
- ``pages`` — one entry per :class:`ExecutionTask`, with the
  property values shaped as Notion expects them.

A future MKT-* block can either (a) hand this payload to a Notion
SDK call, or (b) ship it through n8n / MCP — both options are
explicitly out of scope here. We just produce the data.
"""

from __future__ import annotations

from typing import Any

from .models import (
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
)

# Notion select option colors — applied via ``_option`` below.
_STATUS_COLORS: dict[str, str] = {
    "todo": "default",
    "blocked": "red",
    "needs_review": "orange",
    "approved": "blue",
    "ready": "green",
    "done": "gray",
}

_PRIORITY_COLORS: dict[str, str] = {
    "high": "red",
    "medium": "orange",
    "low": "default",
}

_CATEGORY_COLORS: dict[str, str] = {
    "approval": "red",
    "seo": "blue",
    "email": "purple",
    "social": "pink",
    "design": "yellow",
    "publishing": "green",
    "measurement": "brown",
    "calendar": "gray",
    "operational": "default",
}


def _option(name: str, color_map: dict[str, str]) -> dict[str, str]:
    return {"name": name, "color": color_map.get(name, "default")}


def to_notion_payload(pack: CampaignExecutionTaskPack) -> dict[str, Any]:
    """Build the Notion-shaped payload from a task pack.

    Pure: same pack → same payload. No I/O, no Notion SDK import,
    no network call.
    """
    return {
        "schema_version": "notion-export.v1",
        "source_pack": {
            "pack_id": pack.pack_id,
            "contract_version": pack.contract_version,
            "client_slug": pack.client_slug,
            "report_id": pack.report_id,
            "approval_pack_id": pack.approval_pack_id,
            "creative_pack_id": pack.creative_pack_id,
            "visual_pack_id": pack.visual_pack_id,
            "blocks_publish": pack.blocks_publish,
            "generated_at": pack.created_at.isoformat(),
        },
        "database": _build_database_schema(pack),
        "pages": [_build_page(t) for t in pack.tasks],
    }


def _build_database_schema(pack: CampaignExecutionTaskPack) -> dict[str, Any]:
    return {
        "title": f"Campaign Tasks — {pack.client_slug}",
        "properties": {
            "Name": {"title": {}},
            "Status": {
                "select": {
                    "options": [_option(s.value, _STATUS_COLORS) for s in TaskState]
                }
            },
            "Priority": {
                "select": {
                    "options": [_option(p.value, _PRIORITY_COLORS) for p in TaskPriority]
                }
            },
            "Category": {
                "select": {
                    "options": [_option(c.value, _CATEGORY_COLORS) for c in TaskCategory]
                }
            },
            "Channel": {"rich_text": {}},
            "Asset Kind": {"rich_text": {}},
            "Asset Ref": {"rich_text": {}},
            "Due Date": {"date": {}},
            "Depends On": {"rich_text": {}},
            "Owner Hint": {"rich_text": {}},
            "Description": {"rich_text": {}},
            "Blocked Reason": {"rich_text": {}},
            "Task ID": {"rich_text": {}},
        },
    }


def _build_page(task: ExecutionTask) -> dict[str, Any]:
    """Convert one task to Notion page-properties shape."""
    return {
        "properties": {
            "Name": {"title": [_text(task.title)]},
            "Status": {"select": {"name": task.state.value}},
            "Priority": {"select": {"name": task.priority.value}},
            "Category": {"select": {"name": task.category.value}},
            "Channel": {"rich_text": [_text(task.channel)] if task.channel else []},
            "Asset Kind": {"rich_text": [_text(task.asset_kind)] if task.asset_kind else []},
            "Asset Ref": {"rich_text": [_text(task.asset_ref)] if task.asset_ref else []},
            "Due Date": (
                {"date": {"start": task.due_date.isoformat()}}
                if task.due_date is not None
                else {"date": None}
            ),
            "Depends On": {
                "rich_text": (
                    [_text(", ".join(task.depends_on))] if task.depends_on else []
                )
            },
            "Owner Hint": {
                "rich_text": [_text(task.owner_hint)] if task.owner_hint else []
            },
            "Description": {
                "rich_text": [_text(task.description)] if task.description else []
            },
            "Blocked Reason": {
                "rich_text": (
                    [_text(task.blocked_reason)] if task.blocked_reason else []
                )
            },
            "Task ID": {"rich_text": [_text(task.task_id)]},
        }
    }


def _text(content: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": content}}


__all__ = ["to_notion_payload"]
