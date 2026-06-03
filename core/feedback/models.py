"""Pydantic models for the Campaign Feedback Pack (MKT-6B).

Contract: ``campaign-feedback-pack.v1``.

The pack is a deliverable the agency hands to the client after
analyzing one campaign cycle. It carries:

- Suggested tasks for the next cycle, derived from analytics.
- Channel-level priority adjustments based on actual performance.
- Concrete content suggestions (repeat what worked, pause what
  didn't, improve the mid-tier).
- SEO recommendations from Search Console data.
- Per-channel (email + social) recommendations from open rates,
  engagement etc.
- A short executive summary for the client review meeting.

Cardinal rule: **suggestions only**. Nothing in this pack
mutates a campaign automatically. A human reads, decides,
and acts.

No URL / token / credential field on any model in this layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

CAMPAIGN_FEEDBACK_PACK_VERSION = "campaign-feedback-pack.v1"
CAMPAIGN_FEEDBACK_PACK_KIND = "campaign_feedback_pack"
SINGLETON_ID = "current"


# ============ Enums ============

class SuggestedTaskCategory(StrEnum):
    """Maps 1:1 to the MKT-4E TaskCategory enum so a future
    sync block can fold these into the execution task pack."""

    OPTIMIZATION = "optimization"
    SEO = "seo"
    CONTENT = "content"
    EMAIL = "email"
    SOCIAL = "social"
    MEASUREMENT = "measurement"
    OPERATIONAL = "operational"


class SuggestedTaskPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChannelPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    PAUSE = "pause"


class ContentSuggestionKind(StrEnum):
    REPEAT = "repeat"
    IMPROVE = "improve"
    PAUSE = "pause"


# ============ Atomic pieces ============

class SuggestedTask(DomainModel):
    """One task the feedback pack suggests adding to the next
    campaign cycle. Shape mirrors MKT-4E's ExecutionTask so a
    future sync block can promote it directly."""

    task_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    category: SuggestedTaskCategory
    priority: SuggestedTaskPriority
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_owner: str | None = Field(default=None, max_length=64)
    channel: str | None = Field(default=None, max_length=64)
    content_ref: str | None = Field(default=None, max_length=400)
    evidence_refs: list[str] = Field(default_factory=list)
    """Free-form back-references to source recommendation_ids,
    channel summary entries, SEO opportunity rows."""


class ChannelAdjustment(DomainModel):
    """A channel whose priority in the next cycle should change
    based on observed performance."""

    channel: Annotated[str, Field(min_length=1, max_length=64)]
    current_priority: ChannelPriority | None = None
    """Best-effort: the planner reads this from
    ``CampaignStrategyReport.channel_recommendation`` when
    available."""

    new_priority: ChannelPriority
    rationale: Annotated[str, Field(min_length=1, max_length=400)]
    evidence_refs: list[str] = Field(default_factory=list)


class ContentSuggestion(DomainModel):
    """A repeat / improve / pause suggestion targeting one
    specific content piece or piece pattern."""

    kind: ContentSuggestionKind
    content_ref: str | None = Field(default=None, max_length=400)
    channel: str | None = Field(default=None, max_length=64)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_next_step: Annotated[str, Field(min_length=1, max_length=400)]
    evidence_refs: list[str] = Field(default_factory=list)


class SEORecommendation(DomainModel):
    """One SEO action lifted from the analytics SEO opportunities
    + cross-referenced (best-effort) with strategy keywords."""

    query: str | None = Field(default=None, max_length=400)
    page: str | None = Field(default=None, max_length=400)
    priority: SuggestedTaskPriority
    suggested_action: Annotated[str, Field(min_length=1, max_length=400)]
    rationale: Annotated[str, Field(min_length=1, max_length=400)]
    opportunity_score: float = Field(ge=0.0)
    evidence_refs: list[str] = Field(default_factory=list)


class EmailRecommendation(DomainModel):
    """Recommendation tied to the email channel. Derived from
    open/click rates in the metrics snapshot when available."""

    campaign_ref: str | None = Field(default=None, max_length=400)
    open_rate: float | None = Field(default=None, ge=0.0, le=1.5)
    click_rate: float | None = Field(default=None, ge=0.0, le=1.5)
    suggested_action: Annotated[str, Field(min_length=1, max_length=400)]
    rationale: Annotated[str, Field(min_length=1, max_length=400)]
    priority: SuggestedTaskPriority
    evidence_refs: list[str] = Field(default_factory=list)


class SocialRecommendation(DomainModel):
    """Recommendation tied to a social channel."""

    channel: Annotated[str, Field(min_length=1, max_length=64)]
    content_ref: str | None = Field(default=None, max_length=400)
    suggested_action: Annotated[str, Field(min_length=1, max_length=400)]
    rationale: Annotated[str, Field(min_length=1, max_length=400)]
    priority: SuggestedTaskPriority
    evidence_refs: list[str] = Field(default_factory=list)


class ExecutiveSummary(DomainModel):
    """A short client-facing summary the operator can read aloud
    at the review meeting. Never auto-sent — only persisted."""

    headline: Annotated[str, Field(min_length=1, max_length=240)]
    paragraphs: list[str] = Field(default_factory=list)
    """Up to ~3 short paragraphs. Each one is plain text, no
    markdown. The Markdown renderer wraps them in proper
    blockquote / paragraph formatting."""

    suggested_meeting_agenda: list[str] = Field(default_factory=list)


# ============ Stats ============

class FeedbackStats(DomainModel):
    total_suggested_tasks: int = Field(ge=0)
    high_priority_tasks: int = Field(ge=0)
    channel_adjustments: int = Field(ge=0)
    content_suggestions: int = Field(ge=0)
    seo_recommendations: int = Field(ge=0)
    email_recommendations: int = Field(ge=0)
    social_recommendations: int = Field(ge=0)


# ============ Pack ============

class CampaignFeedbackPack(DomainModel):
    """Top-level deliverable for one feedback cycle."""

    contract_version: Literal["campaign-feedback-pack.v1"] = (
        CAMPAIGN_FEEDBACK_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Source references — every pack must name the snapshot it
    # was built from.
    recommendation_pack_id: str | None = None
    recommendation_pack_contract_version: str | None = None
    snapshot_id: str | None = None
    run_summary_id: str | None = None
    task_pack_id: str | None = None
    creative_pack_id: str | None = None
    visual_pack_id: str | None = None
    strategy_report_id: str | None = None

    executive_summary: ExecutiveSummary | None = None
    suggested_tasks: list[SuggestedTask] = Field(default_factory=list)
    channel_adjustments: list[ChannelAdjustment] = Field(default_factory=list)
    content_suggestions: list[ContentSuggestion] = Field(default_factory=list)
    seo_recommendations: list[SEORecommendation] = Field(default_factory=list)
    email_recommendations: list[EmailRecommendation] = Field(default_factory=list)
    social_recommendations: list[SocialRecommendation] = Field(default_factory=list)
    stats: FeedbackStats

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
            len(self.suggested_tasks)
            + len(self.channel_adjustments)
            + len(self.content_suggestions)
            + len(self.seo_recommendations)
            + len(self.email_recommendations)
            + len(self.social_recommendations)
        )

    def tasks_by_category(self, cat: SuggestedTaskCategory) -> list[SuggestedTask]:
        return [t for t in self.suggested_tasks if t.category is cat]


__all__ = [
    "CAMPAIGN_FEEDBACK_PACK_KIND",
    "CAMPAIGN_FEEDBACK_PACK_VERSION",
    "CampaignFeedbackPack",
    "ChannelAdjustment",
    "ChannelPriority",
    "ContentSuggestion",
    "ContentSuggestionKind",
    "EmailRecommendation",
    "ExecutiveSummary",
    "FeedbackStats",
    "SEORecommendation",
    "SINGLETON_ID",
    "SocialRecommendation",
    "SuggestedTask",
    "SuggestedTaskCategory",
    "SuggestedTaskPriority",
]
