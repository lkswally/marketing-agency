"""Pydantic models for the Ads Insights → Feedback bridge (MKT-6G).

One contract:

- ``ads-feedback-bridge-pack.v1`` —
  :class:`AdsFeedbackBridgePack` containing recommendations,
  campaign adjustments, negative-keyword proposals (proposals
  only, never executed) and suggested tasks derived from a
  :class:`GoogleAdsInsightPack`.

No credential / customer-id / token field appears on any
persisted model.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

ADS_FEEDBACK_BRIDGE_PACK_VERSION = "ads-feedback-bridge-pack.v1"
ADS_FEEDBACK_BRIDGE_PACK_KIND = "ads_feedback_bridge_pack"
SINGLETON_ID = "current"


# ============ Enums ============


class AdsRecommendationKind(StrEnum):
    """Why the recommendation fired. Mirrors :class:`AdsInsightKind`
    1:1 so traceability is straightforward."""

    PAUSE_REVIEW = "pause_review"
    REVIEW_CAMPAIGN = "review_campaign"
    REVIEW_AD_GROUP = "review_ad_group"
    REVIEW_LANDING = "review_landing"
    SCALE_OPPORTUNITY = "scale_opportunity"
    IMPROVE_AD_COPY = "improve_ad_copy"
    BUDGET_REVIEW = "budget_review"
    NEGATIVE_KEYWORD_PROPOSAL = "negative_keyword_proposal"


class AdsRecommendationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdsAdjustmentKind(StrEnum):
    """High-level direction for a campaign-level adjustment.

    These are *suggestions* — the bridge never applies them.
    """

    PAUSE_REVIEW = "pause_review"
    """Operator should consider pausing the campaign for review."""

    SCALE_REVIEW = "scale_review"
    """Operator should consider scaling budget after review."""

    REALLOCATE_REVIEW = "reallocate_review"
    """Operator should consider reallocating budget across campaigns."""

    OPTIMIZE_REVIEW = "optimize_review"
    """Operator should consider creative / landing / targeting tweaks."""


# ============ Atomic pieces ============


class AdsRecommendation(DomainModel):
    """One Google Ads recommendation lifted from an insight."""

    recommendation_id: str = Field(default_factory=new_id)
    kind: AdsRecommendationKind
    priority: AdsRecommendationPriority
    title: Annotated[str, Field(min_length=1, max_length=200)]
    rationale: Annotated[str, Field(min_length=1, max_length=800)]
    suggested_action: Annotated[str, Field(min_length=1, max_length=400)]
    """Free-form sentence the operator can apply manually."""

    campaign_id: str | None = Field(default=None, max_length=64)
    ad_group_id: str | None = Field(default=None, max_length=64)
    content_ref: str | None = Field(default=None, max_length=200)
    dimension: str | None = Field(default=None, max_length=240)
    evidence_refs: list[str] = Field(default_factory=list)
    """Back-references to source insight_ids."""


class AdsCampaignAdjustment(DomainModel):
    """A campaign-level adjustment suggested for the next cycle."""

    campaign_id: str | None = Field(default=None, max_length=64)
    dimension: str | None = Field(default=None, max_length=240)
    kind: AdsAdjustmentKind
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_next_step: Annotated[str, Field(min_length=1, max_length=400)]
    evidence_refs: list[str] = Field(default_factory=list)


class AdsKeywordProposal(DomainModel):
    """A keyword the operator may want to add as a *negative*
    keyword on the next cycle.

    **Proposal only.** The bridge never adds negative keywords to
    Google Ads. The operator reviews and decides.
    """

    keyword: Annotated[str, Field(min_length=1, max_length=200)]
    """The candidate term. May be empty in practice because search-
    term data is not yet available (P-6E.1)."""

    proposed_as: Literal["negative_keyword"] = "negative_keyword"
    """Locked to ``negative_keyword`` in v1 of this contract — there
    is no ``positive_keyword`` variant yet."""

    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    campaign_id: str | None = Field(default=None, max_length=64)
    ad_group_id: str | None = Field(default=None, max_length=64)
    evidence_refs: list[str] = Field(default_factory=list)


class AdsSuggestedTask(DomainModel):
    """Mirrors MKT-6B :class:`SuggestedTask` so the next cycle's
    feedback pack can fold these in (P-6G.1).

    The shape also matches MKT-4E :class:`ExecutionTask` so a
    future opt-in promoter can lift them into the execution task
    pack directly.
    """

    task_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    category: Annotated[str, Field(min_length=1, max_length=32)]
    """Maps to MKT-6B ``SuggestedTaskCategory``. The bridge emits
    one of: ``optimization``, ``content``, ``operational``,
    ``measurement``."""

    priority: AdsRecommendationPriority
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_owner: str | None = Field(default=None, max_length=64)
    channel: str = Field(default="google_ads", max_length=64)
    content_ref: str | None = Field(default=None, max_length=200)
    evidence_refs: list[str] = Field(default_factory=list)


# ============ Stats ============


class AdsBridgeStats(DomainModel):
    total_recommendations: int = Field(ge=0)
    total_campaign_adjustments: int = Field(ge=0)
    total_keyword_proposals: int = Field(ge=0)
    total_suggested_tasks: int = Field(ge=0)
    by_recommendation_kind: dict[str, int] = Field(default_factory=dict)
    by_recommendation_priority: dict[str, int] = Field(default_factory=dict)
    by_adjustment_kind: dict[str, int] = Field(default_factory=dict)
    insights_consumed: int = Field(ge=0)


# ============ Pack ============


class AdsFeedbackBridgePack(DomainModel):
    """Output of one ``mkt ads-feedback`` invocation."""

    contract_version: Literal["ads-feedback-bridge-pack.v1"] = (
        ADS_FEEDBACK_BRIDGE_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    insight_pack_id: str = Field(min_length=1)
    insight_pack_contract_version: str = Field(min_length=1)
    snapshot_id: str | None = Field(default=None, max_length=64)

    # Optional cross-references — populated best-effort.
    feedback_pack_id: str | None = Field(default=None, max_length=64)
    execution_task_pack_id: str | None = Field(default=None, max_length=64)
    iteration_plan_id: str | None = Field(default=None, max_length=64)

    recommendations: list[AdsRecommendation] = Field(default_factory=list)
    campaign_adjustments: list[AdsCampaignAdjustment] = Field(default_factory=list)
    keyword_proposals: list[AdsKeywordProposal] = Field(default_factory=list)
    suggested_tasks: list[AdsSuggestedTask] = Field(default_factory=list)
    executive_summary: str | None = Field(default=None, max_length=2000)

    stats: AdsBridgeStats
    rule_set_id: str | None = None
    created_at: datetime

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


__all__ = [
    "ADS_FEEDBACK_BRIDGE_PACK_KIND",
    "ADS_FEEDBACK_BRIDGE_PACK_VERSION",
    "AdsAdjustmentKind",
    "AdsBridgeStats",
    "AdsCampaignAdjustment",
    "AdsFeedbackBridgePack",
    "AdsKeywordProposal",
    "AdsRecommendation",
    "AdsRecommendationKind",
    "AdsRecommendationPriority",
    "AdsSuggestedTask",
    "SINGLETON_ID",
]
