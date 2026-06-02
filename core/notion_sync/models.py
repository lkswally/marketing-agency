"""Pydantic models for the Notion sync plan (MKT-5A).

Contract: ``notion-sync-plan.v1``.

The plan models WHAT a future synchroniser would do — never what it
did. There is no field for "page_id returned by Notion" because no
page is ever created. The same applies to the database: we describe
the recommended schema, not a created database id.

Notion documented limits referenced by the validator
(:mod:`.planner`):

- Title property content: 2000 chars
- Rich text content: 2000 chars per block
- Select option name: 100 chars (we cap at 100)
- Per database: 100 properties max
- ``url`` property value: 2000 chars
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

NOTION_SYNC_PLAN_VERSION = "notion-sync-plan.v1"


# ============ Enums ============

class PlannedAction(StrEnum):
    """What the future synchroniser WOULD do for a given task."""

    CREATE = "create"
    """A new page would be created in the Notion database."""

    SKIP_BLOCKED = "skip_blocked"
    """The task is BLOCKED upstream; the synchroniser should mark
    it as such but NOT progress its state."""

    SKIP_INVALID = "skip_invalid"
    """The task would not validate against Notion's limits — the
    sync would skip it rather than fail mid-batch."""


class NotionPropertyType(StrEnum):
    """Subset of Notion property types we emit. The full Notion API
    has more (formula, rollup, relation, etc.); only the ones we
    actually use for tasks live here."""

    TITLE = "title"
    RICH_TEXT = "rich_text"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    DATE = "date"
    CHECKBOX = "checkbox"
    URL = "url"


class NotionPlanIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ============ Property mapping ============

class NotionPropertyMapping(DomainModel):
    """One row in the database schema, with a mapping back to the
    source task field."""

    notion_name: Annotated[str, Field(min_length=1, max_length=120)]
    """The exact property name as it would appear in Notion."""

    notion_type: NotionPropertyType
    source_field: Annotated[str, Field(min_length=1, max_length=120)]
    """The :class:`ExecutionTask` attribute (or ``"pack.<x>"``) that
    feeds this property."""

    required: bool = False
    notes: str | None = Field(default=None, max_length=500)
    select_options: list[str] = Field(default_factory=list)
    """For ``SELECT`` / ``MULTI_SELECT`` only — the documented
    options. Empty for free-text properties."""


# ============ Per-record plan ============

class NotionPlannedRecord(DomainModel):
    """What the synchroniser would write (or skip) for one task."""

    task_id: Annotated[str, Field(min_length=1, max_length=120)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    action: PlannedAction
    reason: str | None = Field(default=None, max_length=400)
    """Human-readable explanation when ``action`` is not ``CREATE``."""

    proposed_status: Annotated[str, Field(min_length=1, max_length=32)]
    """The ``Status`` select value the synchroniser would assign."""

    proposed_priority: Annotated[str, Field(min_length=1, max_length=16)]
    proposed_category: Annotated[str, Field(min_length=1, max_length=24)]
    field_count: int = Field(ge=0)
    """Number of mapped properties the record would carry. Useful
    to spot tasks that would be created with very few fields."""


# ============ Issues ============

class NotionPlanIssue(DomainModel):
    """A validation finding raised by the planner."""

    issue_id: str = Field(default_factory=new_id)
    severity: NotionPlanIssueSeverity
    code: Annotated[str, Field(min_length=1, max_length=40)]
    """Stable identifier so a future sync block can hide / promote
    specific issues. E.g. ``"value_too_long"``,
    ``"missing_required_field"``."""

    message: Annotated[str, Field(min_length=1, max_length=400)]
    task_id: str | None = None
    """Set when the issue is per-task; None when it is a global
    concern (e.g. database has zero properties)."""

    field: str | None = None
    mitigation: str | None = Field(default=None, max_length=400)


# ============ Recommended database ============

class NotionRecommendedDatabase(DomainModel):
    """Shape of the database the sync would create. Mirrors what
    the MKT-4E ``to_notion_payload`` already produces but adds
    explicit notes / required flags that the sync tool needs."""

    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = Field(default=None, max_length=800)
    property_mappings: list[NotionPropertyMapping] = Field(default_factory=list)
    icon: str | None = Field(default=None, max_length=8)
    """Emoji or shortcode; the sync tool may set the database icon."""

    notes: list[str] = Field(default_factory=list)


# ============ Stats ============

class NotionSyncStats(DomainModel):
    """Summary numbers — easy to assert on in tests + render in MD."""

    total_tasks: int = Field(ge=0)
    would_create: int = Field(ge=0)
    skip_blocked: int = Field(ge=0)
    skip_invalid: int = Field(ge=0)
    issues_total: int = Field(ge=0)
    issues_error: int = Field(ge=0)
    issues_warning: int = Field(ge=0)
    issues_info: int = Field(ge=0)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    by_state: dict[str, int] = Field(default_factory=dict)


# ============ Plan ============

class NotionSyncPlan(DomainModel):
    """End-to-end dry-run plan for syncing one campaign to Notion."""

    contract_version: Literal["notion-sync-plan.v1"] = NOTION_SYNC_PLAN_VERSION
    plan_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Source references — every plan must name the pack snapshot it
    # was built from.
    task_pack_id: str = Field(min_length=1)
    task_pack_contract_version: str = Field(min_length=1)
    notion_payload_schema_version: Annotated[
        str, Field(min_length=1, max_length=40)
    ]

    # Bookkeeping flags inherited from the task pack so consumers
    # don't have to re-load it.
    blocks_publish: bool = False
    upstream_overall_state: str | None = None

    recommended_database: NotionRecommendedDatabase
    planned_records: list[NotionPlannedRecord] = Field(default_factory=list)
    issues: list[NotionPlanIssue] = Field(default_factory=list)
    stats: NotionSyncStats

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
    def total_records(self) -> int:
        return len(self.planned_records)

    def issues_for(self, severity: NotionPlanIssueSeverity) -> list[NotionPlanIssue]:
        return [i for i in self.issues if i.severity is severity]

    def has_errors(self) -> bool:
        return any(i.severity is NotionPlanIssueSeverity.ERROR for i in self.issues)


__all__ = [
    "NOTION_SYNC_PLAN_VERSION",
    "NotionPlanIssue",
    "NotionPlanIssueSeverity",
    "NotionPlannedRecord",
    "NotionPropertyMapping",
    "NotionPropertyType",
    "NotionRecommendedDatabase",
    "NotionSyncPlan",
    "NotionSyncStats",
    "PlannedAction",
]
