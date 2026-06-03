"""Pydantic models for the n8n execution payload (MKT-5C).

Contract: ``n8n-execution-payload.v1``.

Each :class:`N8nAction` carries a self-contained ``payload`` dict
shaped exactly as a future n8n webhook would receive it. The dict
is opaque from this model's perspective (``dict[str, Any]``) but
shaped consistently by the planner so a webhook on the other side
can validate it. The model only pins the envelope: action_type,
status, target_webhook hint, source references.

No HTTP call. No webhook URL is ever read or stored. The
``target_webhook`` field is a *hint* (e.g. ``"email_drafts"``) so
the future sync tool knows which n8n workflow this payload would
be posted to — never a real URL.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

N8N_EXECUTION_PAYLOAD_VERSION = "n8n-execution-payload.v1"


# ============ Enums ============

class N8nActionType(StrEnum):
    """Action types the planner emits, mapping 1:1 to the user's
    MKT-5C spec."""

    EMAIL_DRAFT = "email_draft"
    SOCIAL_POST_DRAFT = "social_post_draft"
    TELEGRAM_NOTIFICATION = "telegram_notification"
    DRIVE_ASSET_FOLDER = "drive_asset_folder"
    NOTION_STATUS_UPDATE = "notion_status_update"
    CAMPAIGN_REPORT_NOTIFICATION = "campaign_report_notification"


class N8nActionStatus(StrEnum):
    """Per-action lifecycle. The planner only emits ``planned`` or
    ``blocked``; the other values are placeholders for a future
    real-sync block that records what n8n actually did."""

    PLANNED = "planned"
    """The action would be POSTed to its webhook by a future block."""

    BLOCKED = "blocked"
    """Upstream pack blocks publish; the action is recorded for
    visibility but a future sync must NOT trigger it."""

    SKIPPED = "skipped"
    """Reserved for future use (operator override, dry-run skip)."""

    DISPATCHED = "dispatched"
    """Reserved for future use (real sync records this on success)."""

    FAILED = "failed"
    """Reserved for future use (real sync records this on error)."""


# ============ Action ============

class N8nAction(DomainModel):
    """One self-contained payload addressed to one n8n webhook."""

    action_id: str = Field(default_factory=new_id)
    action_type: N8nActionType
    status: N8nActionStatus = N8nActionStatus.PLANNED

    target_webhook: Annotated[str, Field(min_length=1, max_length=80)]
    """Logical webhook name (NOT a URL). Example values:
    ``"email_drafts"``, ``"social_drafts"``, ``"telegram_alerts"``,
    ``"drive_folders"``, ``"notion_updates"``,
    ``"campaign_reports"``. The future sync tool maps each name to
    a real URL from its own config — never from this module."""

    source_kind: str | None = Field(default=None, max_length=64)
    """Upstream artifact kind that originated this action (e.g.
    ``"creative_asset_pack.email"``, ``"notion_sync_report"``,
    ``"campaign_run_summary"``)."""

    source_ref: str | None = Field(default=None, max_length=200)
    """Stable id of the source item so a downstream tool can join
    back (e.g. an EmailAsset.asset_id, a notion page_id)."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """The actual JSON the future sync tool would POST. Shape is
    enforced by the planner per action_type but stored as a free
    dict so the contract can evolve without bumping this model."""

    blocked_reason: str | None = Field(default=None, max_length=400)
    """Populated when ``status == BLOCKED``."""


# ============ Stats ============

class N8nPayloadStats(DomainModel):
    total_actions: int = Field(ge=0)
    planned: int = Field(ge=0)
    blocked: int = Field(ge=0)
    by_type: dict[str, int] = Field(default_factory=dict)


# ============ Payload (top-level) ============

class N8nExecutionPayload(DomainModel):
    """The dry-run payload bundle for one campaign cycle."""

    contract_version: Literal["n8n-execution-payload.v1"] = (
        N8N_EXECUTION_PAYLOAD_VERSION
    )
    payload_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Source references — every payload must name the snapshot it
    # was built from. ``None`` when the corresponding upstream pack
    # is missing for the client.
    run_summary_id: str | None = None
    run_summary_contract_version: str | None = None
    task_pack_id: str | None = None
    task_pack_contract_version: str | None = None
    creative_pack_id: str | None = None
    creative_pack_contract_version: str | None = None
    visual_pack_id: str | None = None
    visual_pack_contract_version: str | None = None
    notion_sync_report_id: str | None = None
    notion_sync_report_contract_version: str | None = None

    blocks_publish: bool = False

    actions: list[N8nAction] = Field(default_factory=list)
    stats: N8nPayloadStats

    created_at: datetime
    rule_set_id: str | None = None

    # ---------- validators ----------

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC)")
        return v

    # ---------- helpers ----------

    @property
    def total_actions(self) -> int:
        return len(self.actions)

    def actions_of_type(self, kind: N8nActionType) -> list[N8nAction]:
        return [a for a in self.actions if a.action_type is kind]

    def blocked_actions(self) -> list[N8nAction]:
        return [a for a in self.actions if a.status is N8nActionStatus.BLOCKED]


__all__ = [
    "N8N_EXECUTION_PAYLOAD_VERSION",
    "N8nAction",
    "N8nActionStatus",
    "N8nActionType",
    "N8nExecutionPayload",
    "N8nPayloadStats",
]
