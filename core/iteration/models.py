"""Pydantic models for the Next Campaign Iteration Plan (MKT-6C).

Contract: ``next-campaign-iteration-plan.v1``.

Plan sections, mapping 1:1 to the user's MKT-6C request:

- ``actions`` — repeat / pause / improve / create_new decisions,
  plus channel_promote / channel_pause adjustments.
- ``new_content_ideas`` — SEO / social / email pitches for the
  next cycle.
- ``ab_test_hypotheses`` — explicit A vs B variants with
  success criteria.
- ``calendar`` — week-by-week suggested cadence for the next
  cycle.
- ``suggested_tasks`` — operational tasks the agency can
  promote into the next execution task pack.
- ``executive_summary`` — short client-facing narrative.

No URL / token / credential field on any model. The plan is
suggestions only; nothing in it triggers a real change.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

NEXT_CAMPAIGN_ITERATION_PLAN_VERSION = "next-campaign-iteration-plan.v1"
NEXT_CAMPAIGN_ITERATION_PLAN_KIND = "next_campaign_iteration_plan"
SINGLETON_ID = "current"


# ============ Enums ============

class IterationActionKind(StrEnum):
    REPEAT_PIECE = "repeat_piece"
    PAUSE_PIECE = "pause_piece"
    IMPROVE_PIECE = "improve_piece"
    CREATE_NEW = "create_new"
    CHANNEL_PROMOTE = "channel_promote"
    CHANNEL_PAUSE = "channel_pause"


class IterationActionPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NewContentKind(StrEnum):
    SEO_ARTICLE = "seo_article"
    SOCIAL_POST = "social_post"
    EMAIL_DRAFT = "email_draft"
    LANDING_PAGE = "landing_page"
    REELS_SCRIPT = "reels_script"


# ============ Atomic pieces ============

class IterationAction(DomainModel):
    """One concrete decision for the next cycle."""

    action_id: str = Field(default_factory=new_id)
    kind: IterationActionKind
    priority: IterationActionPriority
    title: Annotated[str, Field(min_length=1, max_length=200)]
    target_ref: str | None = Field(default=None, max_length=400)
    """Best-effort reference to the piece or channel the action
    targets (asset_id, content_ref, channel name)."""

    channel: str | None = Field(default=None, max_length=64)
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_next_step: Annotated[str, Field(min_length=1, max_length=400)]
    evidence_refs: list[str] = Field(default_factory=list)


class NewContentIdea(DomainModel):
    """A pitch for a new piece to add to the next cycle."""

    idea_id: str = Field(default_factory=new_id)
    kind: NewContentKind
    title: Annotated[str, Field(min_length=1, max_length=200)]
    channel: str | None = Field(default=None, max_length=64)
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    angle: str | None = Field(default=None, max_length=400)
    """The hook / angle the agency should aim for."""

    target_audience: str | None = Field(default=None, max_length=200)
    priority: IterationActionPriority = IterationActionPriority.MEDIUM
    evidence_refs: list[str] = Field(default_factory=list)


class ABTestHypothesis(DomainModel):
    """One A/B test the next cycle can include."""

    hypothesis_id: str = Field(default_factory=new_id)
    surface: Annotated[str, Field(min_length=1, max_length=64)]
    """e.g. ``"email_subject"``, ``"social_hook"``,
    ``"landing_headline"``."""

    variant_a: Annotated[str, Field(min_length=1, max_length=400)]
    variant_b: Annotated[str, Field(min_length=1, max_length=400)]
    success_metric: Annotated[str, Field(min_length=1, max_length=120)]
    success_threshold: Annotated[str, Field(min_length=1, max_length=120)]
    """Free-form (``"open rate ≥ 25%"``, ``"CTR uplift ≥ 20%"``).
    The reviewer interprets, not the planner."""

    rationale: Annotated[str, Field(min_length=1, max_length=400)]
    evidence_refs: list[str] = Field(default_factory=list)


class IterationCalendarEntry(DomainModel):
    """One row in the suggested calendar for the next cycle."""

    week: int = Field(ge=1, le=52)
    suggested_date: date | None = None
    channel: Annotated[str, Field(min_length=1, max_length=64)]
    piece_type: Annotated[str, Field(min_length=1, max_length=64)]
    note: str | None = Field(default=None, max_length=200)
    action_ref: str | None = Field(default=None, max_length=120)
    """Optional back-ref to an ``IterationAction.action_id`` so the
    operator can trace the calendar entry to its source decision."""


class IterationExecutiveSummary(DomainModel):
    headline: Annotated[str, Field(min_length=1, max_length=240)]
    paragraphs: list[str] = Field(default_factory=list)
    suggested_meeting_agenda: list[str] = Field(default_factory=list)


class SuggestedIterationTask(DomainModel):
    """A task the agency should run during the next cycle. Shape
    is intentionally close to MKT-4E ``ExecutionTask`` so a
    future promotion block can fold these directly into the next
    `mkt build-tasks` pack."""

    task_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    category: Annotated[str, Field(min_length=1, max_length=24)]
    priority: IterationActionPriority
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_owner: str | None = Field(default=None, max_length=64)
    channel: str | None = Field(default=None, max_length=64)
    evidence_refs: list[str] = Field(default_factory=list)


# ============ Stats ============

class IterationStats(DomainModel):
    total_actions: int = Field(ge=0)
    repeats: int = Field(ge=0)
    pauses: int = Field(ge=0)
    improves: int = Field(ge=0)
    creates: int = Field(ge=0)
    channel_adjustments: int = Field(ge=0)
    new_content_ideas: int = Field(ge=0)
    ab_test_hypotheses: int = Field(ge=0)
    calendar_entries: int = Field(ge=0)
    suggested_tasks: int = Field(ge=0)


# ============ Pack ============

class NextCampaignIterationPlan(DomainModel):
    """Top-level deliverable for one iteration plan."""

    contract_version: Literal["next-campaign-iteration-plan.v1"] = (
        NEXT_CAMPAIGN_ITERATION_PLAN_VERSION
    )
    plan_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Source references — every plan must name the snapshot it
    # was built from.
    feedback_pack_id: str = Field(min_length=1)
    feedback_pack_contract_version: str = Field(min_length=1)
    recommendation_pack_id: str | None = None
    snapshot_id: str | None = None
    run_summary_id: str | None = None
    task_pack_id: str | None = None
    creative_pack_id: str | None = None
    visual_pack_id: str | None = None
    strategy_report_id: str | None = None

    executive_summary: IterationExecutiveSummary | None = None
    actions: list[IterationAction] = Field(default_factory=list)
    new_content_ideas: list[NewContentIdea] = Field(default_factory=list)
    ab_test_hypotheses: list[ABTestHypothesis] = Field(default_factory=list)
    calendar: list[IterationCalendarEntry] = Field(default_factory=list)
    suggested_tasks: list[SuggestedIterationTask] = Field(default_factory=list)
    stats: IterationStats

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
    def total_items(self) -> int:
        return (
            len(self.actions)
            + len(self.new_content_ideas)
            + len(self.ab_test_hypotheses)
            + len(self.calendar)
            + len(self.suggested_tasks)
        )

    def actions_of_kind(self, kind: IterationActionKind) -> list[IterationAction]:
        return [a for a in self.actions if a.kind is kind]


__all__ = [
    "ABTestHypothesis",
    "IterationAction",
    "IterationActionKind",
    "IterationActionPriority",
    "IterationCalendarEntry",
    "IterationExecutiveSummary",
    "IterationStats",
    "NEXT_CAMPAIGN_ITERATION_PLAN_KIND",
    "NEXT_CAMPAIGN_ITERATION_PLAN_VERSION",
    "NewContentIdea",
    "NewContentKind",
    "NextCampaignIterationPlan",
    "SINGLETON_ID",
    "SuggestedIterationTask",
]
