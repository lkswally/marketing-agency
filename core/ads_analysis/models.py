"""Pydantic models for the Google Ads analyzer (MKT-6F).

One contract:

- ``google-ads-insight-pack.v1`` —
  :class:`GoogleAdsInsightPack` containing per-ad-group profiles,
  structured insights with explicit suggested actions, and stats
  summarising the analysis.

No credential / token / customer-id field appears on any persisted
model. The pack references rows by their ``content_ref`` only —
the same ``campaign:<id>::ad_group:<id>`` shape the MKT-6E
connector emits.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

GOOGLE_ADS_INSIGHT_PACK_VERSION = "google-ads-insight-pack.v1"
GOOGLE_ADS_INSIGHT_PACK_KIND = "google_ads_insight_pack"

SINGLETON_ID = "current"


# ============ Enums ============


class AdsInsightKind(StrEnum):
    """The kind of detection that fired."""

    HIGH_SPEND_ZERO_CONV = "high_spend_zero_conv"
    HIGH_SPEND_LOW_CONV = "high_spend_low_conv"
    LOW_CTR_HIGH_IMPR = "low_ctr_high_impr"
    GOOD_CTR_LOW_CONV_RATE = "good_ctr_low_conv_rate"
    HIGH_CPA_OUTLIER = "high_cpa_outlier"
    SCALE_CANDIDATE = "scale_candidate"
    REVIEW_CAMPAIGN = "review_campaign"
    REVIEW_AD_GROUP = "review_ad_group"
    REVIEW_LANDING = "review_landing"
    PAUSE_CANDIDATE = "pause_candidate"
    IMPROVE_AD_COPY = "improve_ad_copy"
    BUDGET_REVIEW = "budget_review"


class AdsInsightSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdsInsightAction(StrEnum):
    """Suggested next step. The system NEVER applies these — they
    are advisory only for the operator."""

    REVIEW_CAMPAIGN = "review_campaign"
    REVIEW_AD_GROUP = "review_ad_group"
    REVIEW_LANDING = "review_landing"
    PAUSE_CANDIDATE = "pause_candidate"
    SCALE_CANDIDATE = "scale_candidate"
    IMPROVE_AD_COPY = "improve_ad_copy"
    BUDGET_REVIEW = "budget_review"


# ============ Per-ad-group rollup ============


class AdGroupProfile(DomainModel):
    """Aggregated metrics for one ``content_ref`` (campaign + ad_group)."""

    content_ref: Annotated[str, Field(min_length=1, max_length=200)]
    campaign_id: str | None = Field(default=None, max_length=64)
    ad_group_id: str | None = Field(default=None, max_length=64)
    dimension: str | None = Field(default=None, max_length=240)
    """Human-readable ``"<campaign name> / <ad group name>"`` when
    available from the source rows."""

    impressions: float = Field(default=0.0, ge=0.0)
    clicks: float = Field(default=0.0, ge=0.0)
    cost: float = Field(default=0.0, ge=0.0)
    conversions: float = Field(default=0.0, ge=0.0)
    conversions_value: float = Field(default=0.0, ge=0.0)

    ctr: float | None = Field(default=None, ge=0.0, le=2.0)
    """Click-through rate, recomputed from clicks/impressions when
    both are present. ``None`` when impressions == 0."""

    cpc: float | None = Field(default=None, ge=0.0)
    """Average cost per click — ``cost / clicks``. ``None`` when
    clicks == 0."""

    cpa: float | None = Field(default=None, ge=0.0)
    """Average cost per conversion — ``cost / conversions``. ``None``
    when conversions == 0."""

    conversion_rate: float | None = Field(default=None, ge=0.0, le=2.0)
    """Conversion rate — ``conversions / clicks``. ``None`` when
    clicks == 0."""

    sample_rows: int = Field(ge=0)


# ============ Insight ============


class GoogleAdsInsight(DomainModel):
    """One actionable Google Ads insight surfaced by the analyzer."""

    insight_id: str = Field(default_factory=new_id)
    kind: AdsInsightKind
    severity: AdsInsightSeverity
    suggested_action: AdsInsightAction
    title: Annotated[str, Field(min_length=1, max_length=200)]
    rationale: Annotated[str, Field(min_length=1, max_length=800)]
    content_ref: str | None = Field(default=None, max_length=200)
    campaign_id: str | None = Field(default=None, max_length=64)
    ad_group_id: str | None = Field(default=None, max_length=64)
    dimension: str | None = Field(default=None, max_length=240)

    evidence: dict[str, float] = Field(default_factory=dict)
    """Concrete metric values that triggered the insight. Floats
    keyed by metric name (``cost``, ``clicks``, ``ctr`` etc.). The
    renderer surfaces these for review."""

    thresholds_used: dict[str, float] = Field(default_factory=dict)
    """The threshold constants that fired the rule, keyed by name.
    Helps the operator decide whether to override per-tenant
    (P-6F.1)."""


# ============ Stats ============


class AdsInsightStats(DomainModel):
    total_insights: int = Field(ge=0)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_action: dict[str, int] = Field(default_factory=dict)
    ad_groups_profiled: int = Field(ge=0)
    rows_analyzed: int = Field(ge=0)


# ============ Pack ============


class GoogleAdsInsightPack(DomainModel):
    """Output of one ``mkt ads-analyze`` invocation."""

    contract_version: Literal["google-ads-insight-pack.v1"] = (
        GOOGLE_ADS_INSIGHT_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    snapshot_id: str = Field(min_length=1)
    snapshot_contract_version: str = Field(min_length=1)

    profiles: list[AdGroupProfile] = Field(default_factory=list)
    insights: list[GoogleAdsInsight] = Field(default_factory=list)
    stats: AdsInsightStats

    created_at: datetime
    rule_set_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)

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
    "AdGroupProfile",
    "AdsInsightAction",
    "AdsInsightKind",
    "AdsInsightSeverity",
    "AdsInsightStats",
    "GOOGLE_ADS_INSIGHT_PACK_KIND",
    "GOOGLE_ADS_INSIGHT_PACK_VERSION",
    "GoogleAdsInsight",
    "GoogleAdsInsightPack",
    "SINGLETON_ID",
]
