"""Pydantic models for the Campaign Execution Task Pack (MKT-4E).

Contract: ``campaign-execution-task-pack.v1``.

The pack is a flat list of :class:`ExecutionTask` plus header
metadata. Tasks carry priority, state, category, dependencies and
optional per-task references to the underlying asset/channel/piece.

State machine — six values, conservative transitions enforced by
the factory (not by Pydantic):

  todo ── ready ── done
   │       ▲
   │       │
   └─ needs_review ── approved ──┘

  blocked  ← terminal until manually moved (factory may set this
              when an upstream artifact blocks publish OR when a
              dependency is itself blocked)

Priority is a fixed 3-level scale (high / medium / low). Category
groups tasks for the operational view (Markdown + Notion).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

CAMPAIGN_EXECUTION_TASK_PACK_VERSION = "campaign-execution-task-pack.v1"


# ============ Enums ============

class TaskState(StrEnum):
    """Per-task lifecycle. ``blocked`` is the only state the factory
    may emit besides ``todo``; the others are for downstream tools
    (Notion, kanban) to move tasks through manually."""

    TODO = "todo"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    READY = "ready"
    DONE = "done"


class TaskPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskCategory(StrEnum):
    """High-level grouping used in the operational Markdown and in
    the Notion 'Category' select property."""

    APPROVAL = "approval"
    SEO = "seo"
    EMAIL = "email"
    SOCIAL = "social"
    DESIGN = "design"
    PUBLISHING = "publishing"
    MEASUREMENT = "measurement"
    CALENDAR = "calendar"
    OPERATIONAL = "operational"


# ============ Task ============

class ExecutionTask(DomainModel):
    """A single operational unit of work derived from the campaign packs."""

    task_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = Field(default=None, max_length=2000)
    category: TaskCategory
    priority: TaskPriority
    state: TaskState
    channel: str | None = Field(default=None, max_length=64)
    """Channel name (e.g. ``"linkedin"``) when the task is channel-bound."""

    asset_kind: str | None = Field(default=None, max_length=64)
    """Creative asset kind (e.g. ``"social_post"``, ``"reels_script"``)
    when the task targets a specific piece."""

    asset_ref: str | None = Field(default=None, max_length=200)
    """Free-form id of the underlying asset (post_id, email_id, etc.)
    so a downstream tool can join back to the source pack."""

    due_date: date | None = None
    depends_on: list[str] = Field(default_factory=list)
    """Other ``task_id``s that must reach ``done`` before this task can
    move out of ``todo``. The factory never produces cycles."""

    blocked_reason: str | None = Field(default=None, max_length=400)
    """Populated by the factory when ``state == BLOCKED`` so the
    operator sees why."""

    owner_hint: str | None = Field(default=None, max_length=120)
    """Suggested role (e.g. ``"copywriter"``, ``"account_lead"``).
    Never a real person — the operator assigns later."""

    notes: str | None = Field(default=None, max_length=2000)


# ============ Pack ============

class CampaignExecutionTaskPack(DomainModel):
    """The full operational task plan for one campaign cycle."""

    contract_version: Literal["campaign-execution-task-pack.v1"] = (
        CAMPAIGN_EXECUTION_TASK_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Upstream references — every task pack must say which campaign
    # snapshot produced it.
    report_id: str = Field(min_length=1)
    report_contract_version: str = Field(min_length=1)
    approval_pack_id: str | None = None
    approval_pack_contract_version: str | None = None
    creative_pack_id: str | None = None
    creative_pack_contract_version: str | None = None
    visual_pack_id: str | None = None
    visual_pack_contract_version: str | None = None

    # Derivation flags — copied from upstream so consumers don't need
    # to load three more packs to know whether publish is blocked.
    blocks_publish: bool = False
    upstream_overall_state: str | None = None
    """The overall_state value the upstream creative/visual packs
    carry (one of CreativeAssetState). Plain string to avoid
    cross-package enum coupling."""

    tasks: list[ExecutionTask] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
    rule_set_id: str | None = None

    # ---------- validators ----------

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    # ---------- helpers ----------

    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    def count_by_state(self) -> dict[str, int]:
        counts = {s.value: 0 for s in TaskState}
        for t in self.tasks:
            counts[t.state.value] += 1
        return counts

    def count_by_priority(self) -> dict[str, int]:
        counts = {p.value: 0 for p in TaskPriority}
        for t in self.tasks:
            counts[t.priority.value] += 1
        return counts

    def count_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.tasks:
            counts[t.category.value] = counts.get(t.category.value, 0) + 1
        return counts

    def tasks_in_category(self, cat: TaskCategory) -> list[ExecutionTask]:
        return [t for t in self.tasks if t.category is cat]

    def blocked_tasks(self) -> list[ExecutionTask]:
        return [t for t in self.tasks if t.state is TaskState.BLOCKED]


__all__ = [
    "CAMPAIGN_EXECUTION_TASK_PACK_VERSION",
    "CampaignExecutionTaskPack",
    "ExecutionTask",
    "TaskCategory",
    "TaskPriority",
    "TaskState",
]
