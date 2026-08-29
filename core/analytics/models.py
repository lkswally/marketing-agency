"""Pydantic models for the marketing analytics layer (MKT-6A).

Three contracts:

- ``metrics-snapshot.v1`` — :class:`MetricsSnapshot` containing
  per-row normalised metric data accumulated across imports.
- ``analytics-import-report.v1`` — :class:`AnalyticsImportReport`
  documenting one ``mkt import-metrics`` invocation.
- ``optimization-recommendation-pack.v1`` —
  :class:`OptimizationRecommendationPack` with rankings,
  opportunities and explicit recommendations.

No external API. No HTTP. No credential field on any model.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

METRICS_SNAPSHOT_VERSION = "metrics-snapshot.v1"
METRICS_SNAPSHOT_KIND = "metrics_snapshot"

ANALYTICS_IMPORT_REPORT_VERSION = "analytics-import-report.v1"
ANALYTICS_IMPORT_REPORT_KIND = "analytics_import_report"

OPTIMIZATION_RECOMMENDATION_PACK_VERSION = "optimization-recommendation-pack.v1"
OPTIMIZATION_RECOMMENDATION_PACK_KIND = "optimization_recommendation_pack"

SINGLETON_ID = "current"


def snapshot_entity_id(
    source: MetricSource, period_start: date, period_end: date
) -> str:
    """Deterministic memory entity_id for a period-scoped snapshot.

    Format: ``{source}-{YYYY-MM-DD}-{YYYY-MM-DD}``.
    Identical inputs always produce the same string so re-importing the
    same (source, period) appends to the existing snapshot rather than
    creating a new one.
    """
    return f"{source.value}-{period_start.isoformat()}-{period_end.isoformat()}"


def snapshot_id_from_period(
    source: MetricSource, period_start: date, period_end: date
) -> str:
    """Deterministic snapshot_id (model-level UUID substitute) for a period snapshot.

    Uses SHA-256 of the entity_id so the model-level id is also stable
    across re-imports of the same period, enabling idempotent round-trips.
    """
    key = snapshot_entity_id(source, period_start, period_end)
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ============ Enums ============

class MetricSource(StrEnum):
    """Data source the metric row was imported from."""

    GA4 = "ga4"
    SEARCH_CONSOLE = "search_console"
    SOCIAL = "social"
    EMAIL = "email"
    MANUAL = "manual"
    GOOGLE_ADS = "google_ads"


class RecommendationKind(StrEnum):
    REPEAT = "repeat"
    """Campaign / piece worth repeating."""

    PAUSE = "pause"
    """Campaign / piece worth pausing."""

    IMPROVE = "improve"
    """Piece worth iterating on."""

    SEO_OPPORTUNITY = "seo_opportunity"
    """Query / page with low CTR or low position but high impressions."""

    NEXT_ACTION = "next_action"
    """Generic next step suggestion."""


class RecommendationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ============ Row ============

class MetricRow(DomainModel):
    """One normalised metric row. Multiple sources funnel into this
    same shape so the analyzer can treat them uniformly."""

    row_id: str = Field(default_factory=new_id)
    source: MetricSource
    event_date: date | None = None
    """ISO date of the metric event. ``None`` is allowed for
    aggregated rows that don't carry a date dimension."""

    channel: str | None = Field(default=None, max_length=64)
    """Logical channel (``"linkedin"``, ``"newsletter"``,
    ``"organic_search"``, ``"email"`` etc.)."""

    content_ref: str | None = Field(default=None, max_length=400)
    """URL, post_id, email_id, or page slug the metric belongs to."""

    query: str | None = Field(default=None, max_length=400)
    """Search query (Search Console only)."""

    metric_name: Annotated[str, Field(min_length=1, max_length=64)]
    """Lower-snake-case metric name. Common: ``sessions``, ``users``,
    ``clicks``, ``impressions``, ``ctr``, ``position``,
    ``engagement``, ``conversions``, ``opens``, ``bounce_rate``."""

    value: float
    """Numeric value. The analyzer interprets ``ctr`` / ``bounce_rate``
    as 0..1 fractions; ``position`` as integer-ish rank; everything
    else as a count or rate. CSV parsers are forgiving — they
    coerce ``"3.5%"`` to ``0.035`` and ``"1,234"`` to ``1234``."""

    dimension: str | None = Field(default=None, max_length=120)
    """Free-form secondary dimension (``"desktop"`` / ``"mobile"``,
    ``"new_user"`` / ``"returning"``)."""


# ============ Snapshot ============

class MetricsSnapshot(DomainModel):
    """All normalised metric rows for one client. Imports append to
    this snapshot; a new ``mkt import-metrics`` invocation never
    overwrites — the snapshot grows append-only.

    **Time-ranged snapshots (MKT-10B)**

    When ``period_start`` and ``period_end`` are set this snapshot
    represents a specific time window for a single source. The memory
    entity_id is ``snapshot_entity_id(source, period_start, period_end)``
    instead of ``"current"``.  The legacy ``"current"`` singleton is
    always kept up-to-date as a backward-compatible aggregate of all
    imports regardless of period.
    """

    contract_version: Literal["metrics-snapshot.v1"] = METRICS_SNAPSHOT_VERSION
    snapshot_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    rows: list[MetricRow] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_import_id: str | None = None

    # --- period metadata (MKT-10B) ---
    period_start: date | None = None
    period_end: date | None = None
    period_label: str | None = Field(default=None, max_length=64)
    """Human-readable label, e.g. ``"2024-W24"``, ``"2024-Q2"``."""
    source: MetricSource | None = None
    """Primary source for source-scoped period snapshots. ``None`` for
    the ``"current"`` aggregate which may span multiple sources."""

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

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    def rows_by_source(self, source: MetricSource) -> list[MetricRow]:
        return [r for r in self.rows if r.source is source]


# ============ Import report ============

class AnalyticsImportReport(DomainModel):
    """One ``mkt import-metrics`` invocation."""

    contract_version: Literal["analytics-import-report.v1"] = (
        ANALYTICS_IMPORT_REPORT_VERSION
    )
    import_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    source: MetricSource
    file_path: Annotated[str, Field(min_length=1, max_length=400)]
    rows_imported: int = Field(ge=0)
    rows_rejected: int = Field(ge=0)
    rejected_reasons: list[str] = Field(default_factory=list)
    imported_at: datetime

    # --- period metadata (MKT-10B) ---
    period_start: date | None = None
    period_end: date | None = None
    period_label: str | None = Field(default=None, max_length=64)
    period_snapshot_entity_id: str | None = None
    """Memory entity_id of the period-scoped snapshot, if one was written.
    ``None`` when no ``--period-start`` / ``--period-end`` were provided."""

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("imported_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("imported_at must be timezone-aware (UTC)")
        return v


# ============ Analysis summaries ============

class ChannelPerformanceSummary(DomainModel):
    """Per-channel aggregates rolled up across all sources."""

    channel: Annotated[str, Field(min_length=1, max_length=64)]
    total_clicks: float = 0.0
    total_impressions: float = 0.0
    total_engagement: float = 0.0
    total_conversions: float = 0.0
    avg_ctr: float | None = None
    avg_position: float | None = None
    sample_rows: int = Field(ge=0)


class ContentPerformanceSummary(DomainModel):
    """Per-content aggregates."""

    content_ref: Annotated[str, Field(min_length=1, max_length=400)]
    channel: str | None = Field(default=None, max_length=64)
    total_clicks: float = 0.0
    total_impressions: float = 0.0
    total_engagement: float = 0.0
    total_conversions: float = 0.0
    sample_rows: int = Field(ge=0)


class SEOOpportunity(DomainModel):
    """One actionable SEO opportunity surfaced from Search Console
    data."""

    query: str | None = Field(default=None, max_length=400)
    page: str | None = Field(default=None, max_length=400)
    impressions: float = Field(ge=0.0)
    clicks: float = Field(ge=0.0)
    ctr: float | None = Field(default=None, ge=0.0, le=1.5)
    position: float | None = Field(default=None, ge=0.0)
    opportunity_score: float = Field(ge=0.0)
    """Heuristic score: higher = more potential lift if optimised.
    Roughly ``impressions * (target_ctr - current_ctr)`` for
    low-CTR opportunities, ``impressions * (1 / position)`` for
    position-improvement opportunities."""

    reason: Annotated[str, Field(min_length=1, max_length=200)]


class SEOOpportunityReport(DomainModel):
    opportunities: list[SEOOpportunity] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=800)


# ============ Recommendation + Pack ============

class Recommendation(DomainModel):
    """One actionable recommendation surfaced by the analyzer."""

    recommendation_id: str = Field(default_factory=new_id)
    kind: RecommendationKind
    priority: RecommendationPriority
    title: Annotated[str, Field(min_length=1, max_length=200)]
    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    suggested_action: Annotated[str, Field(min_length=1, max_length=400)]
    evidence_refs: list[str] = Field(default_factory=list)
    """Free-form references to source metric_ids, channel names,
    content_refs that back the recommendation. The renderer
    surfaces these for review."""


# Backwards-compatible alias spec'd by the user.
OptimizationRecommendation = Recommendation


class OptimizationRecommendationPack(DomainModel):
    """End-to-end analysis output."""

    contract_version: Literal["optimization-recommendation-pack.v1"] = (
        OPTIMIZATION_RECOMMENDATION_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    snapshot_id: str = Field(min_length=1)
    snapshot_contract_version: str = Field(min_length=1)

    total_rows_analyzed: int = Field(ge=0)
    channels: list[ChannelPerformanceSummary] = Field(default_factory=list)
    top_content: list[ContentPerformanceSummary] = Field(default_factory=list)
    seo_opportunities: SEOOpportunityReport = Field(
        default_factory=SEOOpportunityReport
    )
    best_channel: str | None = Field(default=None, max_length=64)
    worst_channel: str | None = Field(default=None, max_length=64)

    recommendations: list[Recommendation] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    """High-level free-form next steps, one per line."""

    notes: str | None = Field(default=None, max_length=1000)

    created_at: datetime
    rule_set_id: str | None = None

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
    "ANALYTICS_IMPORT_REPORT_KIND",
    "ANALYTICS_IMPORT_REPORT_VERSION",
    "AnalyticsImportReport",
    "ChannelPerformanceSummary",
    "ContentPerformanceSummary",
    "METRICS_SNAPSHOT_KIND",
    "METRICS_SNAPSHOT_VERSION",
    "MetricRow",
    "MetricSource",
    "MetricsSnapshot",
    "OPTIMIZATION_RECOMMENDATION_PACK_KIND",
    "OPTIMIZATION_RECOMMENDATION_PACK_VERSION",
    "OptimizationRecommendation",
    "OptimizationRecommendationPack",
    "Recommendation",
    "RecommendationKind",
    "RecommendationPriority",
    "SEOOpportunity",
    "SEOOpportunityReport",
    "SINGLETON_ID",
    "snapshot_entity_id",
    "snapshot_id_from_period",
]
