"""n8n execution payload planning (MKT-5C) — DRY RUN ONLY.

Contract: ``n8n-execution-payload.v1``.

Builds the per-action payloads that a future n8n integration block
would POST to its webhooks. **Nothing in this module makes an HTTP
call, opens a socket, reads a webhook URL env var, or sends any
real message.** The payload is data on disk + memory; a downstream
sync tool (or a future MKT-* block) is the one that would actually
trigger n8n.

Action types covered:

- ``email_draft`` — one per email asset in the creative pack.
- ``social_post_draft`` — one per social post asset.
- ``telegram_notification`` — one campaign-level notification.
- ``drive_asset_folder`` — one folder-creation hint per visual
  direction (so n8n can mirror the structure in Google Drive).
- ``notion_status_update`` — one per task synced to Notion
  (read from the latest NotionSyncReport).
- ``campaign_report_notification`` — one campaign-level summary.

Blocking semantics inherited from upstream:

- If the campaign blocks publish (ApprovalPack), every action of
  type ``email_draft`` and ``social_post_draft`` is emitted with
  ``status="blocked"`` and an explicit ``blocked_reason``.
- Notifications, folder-setup, and notion-update actions stay
  ``planned`` even when publish is blocked — the operator still
  wants the team alerted and the folder skeleton ready.
"""

from __future__ import annotations

from .models import (
    N8N_EXECUTION_PAYLOAD_VERSION,
    N8nAction,
    N8nActionStatus,
    N8nActionType,
    N8nExecutionPayload,
    N8nPayloadStats,
)
from .planner import (
    DEFAULT_N8N_PLANNER_RULE_SET_ID,
    N8N_EXECUTION_PAYLOAD_KIND,
    SINGLETON_ID,
    N8nPayloadPlanner,
    plan_and_persist,
)
from .renderer import render_markdown_payload

__all__ = [
    "DEFAULT_N8N_PLANNER_RULE_SET_ID",
    "N8N_EXECUTION_PAYLOAD_KIND",
    "N8N_EXECUTION_PAYLOAD_VERSION",
    "N8nAction",
    "N8nActionStatus",
    "N8nActionType",
    "N8nExecutionPayload",
    "N8nPayloadPlanner",
    "N8nPayloadStats",
    "SINGLETON_ID",
    "plan_and_persist",
    "render_markdown_payload",
]
