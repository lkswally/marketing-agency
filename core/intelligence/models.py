"""MKT-10X — Pydantic contracts for market intelligence and UTM tracking.

All models are immutable (frozen=True where appropriate) and validated at
construction time. No network calls, no file I/O in this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from core.domain.base import new_id, utcnow

INTELLIGENCE_CONTRACT_VERSION = "intelligence.v1"
UTM_CONTRACT_VERSION = "utm.v1"

# ---------------------------------------------------------------------------
# Market Intelligence
# ---------------------------------------------------------------------------


class TrendSignal(BaseModel):
    """A trend signal detected from an external source (e.g. Google Trends).

    In dry-run / fixture mode the ``source`` is ``"dry-run"`` and
    ``fetched_at`` reflects the fixture creation time.
    """

    model_config = ConfigDict(frozen=True)

    signal_id: str = Field(default_factory=new_id)
    keyword: Annotated[str, Field(min_length=1, max_length=200)]
    relative_interest: Annotated[float, Field(ge=0.0, le=100.0)]
    """Google Trends–style score: 0–100 relative to peak interest in window."""
    direction: Annotated[str, Field(pattern=r"^(rising|falling|stable)$")]
    region: str = "global"
    source: str = "dry-run"
    fetched_at: datetime = Field(default_factory=utcnow)
    notes: str | None = None


class CompetitorSignal(BaseModel):
    """A point-in-time observation about a competitor.

    ``observed_at`` is when the data was captured; ``source_url`` is the
    page that was observed (may be None for dry-run fixtures).
    """

    model_config = ConfigDict(frozen=True)

    signal_id: str = Field(default_factory=new_id)
    competitor_name: Annotated[str, Field(min_length=1, max_length=200)]
    competitor_url: str | None = None
    observation_type: Annotated[
        str,
        Field(
            pattern=r"^(new_content|pricing_change|new_feature|new_offer|social_activity|other)$"
        ),
    ]
    summary: Annotated[str, Field(min_length=1, max_length=1000)]
    source_url: str | None = None
    observed_at: datetime = Field(default_factory=utcnow)
    confidence: Annotated[str, Field(pattern=r"^(high|medium|low)$")] = "low"
    source: str = "dry-run"


class ContentGap(BaseModel):
    """A content gap: a topic competitors cover that the client does not.

    ``gap_score`` is a 0–100 heuristic combining search interest and
    competitor coverage.
    """

    model_config = ConfigDict(frozen=True)

    gap_id: str = Field(default_factory=new_id)
    topic: Annotated[str, Field(min_length=1, max_length=200)]
    keywords: list[str] = Field(default_factory=list)
    gap_score: Annotated[float, Field(ge=0.0, le=100.0)] = 0.0
    """Higher = bigger opportunity."""
    competitor_coverage: list[str] = Field(default_factory=list)
    """Names of competitors that already cover this topic."""
    recommended_format: str | None = None
    source: str = "dry-run"
    detected_at: datetime = Field(default_factory=utcnow)


class MarketIntelligencePack(BaseModel):
    """Consolidated market intelligence snapshot for one client cycle.

    Persisted under kind=``market_intelligence_pack`` with
    entity_id=``current`` (singleton, same pattern as other packs).
    """

    model_config = ConfigDict(frozen=True)

    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    contract_version: str = INTELLIGENCE_CONTRACT_VERSION
    generated_at: datetime = Field(default_factory=utcnow)

    trend_signals: list[TrendSignal] = Field(default_factory=list)
    competitor_signals: list[CompetitorSignal] = Field(default_factory=list)
    content_gaps: list[ContentGap] = Field(default_factory=list)

    summary: str | None = None
    """Optional free-text summary for the weekly executive report."""


# ---------------------------------------------------------------------------
# UTM Tracking
# ---------------------------------------------------------------------------


class UTMTaggedLink(BaseModel):
    """A single UTM-tagged URL for one channel + piece combination."""

    model_config = ConfigDict(frozen=True)

    link_id: str = Field(default_factory=new_id)
    piece_title: Annotated[str, Field(min_length=1, max_length=300)]
    channel: Annotated[str, Field(min_length=1, max_length=100)]

    base_url: str
    utm_source: Annotated[str, Field(min_length=1, max_length=100)]
    utm_medium: Annotated[str, Field(min_length=1, max_length=100)]
    utm_campaign: Annotated[str, Field(min_length=1, max_length=200)]
    utm_content: Annotated[str, Field(min_length=1, max_length=200)]
    utm_term: str | None = None

    final_url: str
    """base_url with all UTM parameters appended."""

    notes: str | None = None


class TrackingRecommendation(BaseModel):
    """A recommended action to improve UTM tracking coverage."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(default_factory=new_id)
    priority: Annotated[str, Field(pattern=r"^(high|medium|low)$")]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    affected_channels: list[str] = Field(default_factory=list)
    action: str


class UTMPlan(BaseModel):
    """UTM tracking plan for one client campaign cycle.

    Persisted under kind=``utm_plan`` with entity_id=``current``.
    Outputs go to ``outputs/<client_slug>/utm-plan.{md,json}``.
    """

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    contract_version: str = UTM_CONTRACT_VERSION
    generated_at: datetime = Field(default_factory=utcnow)

    campaign_name: str
    period: str
    """Human-readable period label, e.g. ``"2024-Q3"``."""

    tagged_links: list[UTMTaggedLink] = Field(default_factory=list)
    recommendations: list[TrackingRecommendation] = Field(default_factory=list)

    total_links: int = 0
    channels_covered: list[str] = Field(default_factory=list)


__all__ = [
    "INTELLIGENCE_CONTRACT_VERSION",
    "UTM_CONTRACT_VERSION",
    "TrendSignal",
    "CompetitorSignal",
    "ContentGap",
    "MarketIntelligencePack",
    "UTMTaggedLink",
    "TrackingRecommendation",
    "UTMPlan",
]
