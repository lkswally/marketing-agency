"""Pydantic validation tests for the analytics models."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from core.analytics import (
    ANALYTICS_IMPORT_REPORT_VERSION,
    METRICS_SNAPSHOT_VERSION,
    OPTIMIZATION_RECOMMENDATION_PACK_VERSION,
    AnalyticsImportReport,
    ChannelPerformanceSummary,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
    OptimizationRecommendationPack,
    Recommendation,
    SEOOpportunity,
    SEOOpportunityReport,
)
from core.analytics.models import RecommendationKind, RecommendationPriority


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


# ---------- MetricRow ----------

def test_metric_row_minimal() -> None:
    r = MetricRow(source=MetricSource.GA4, metric_name="sessions", value=420.0)
    assert r.event_date is None
    assert r.channel is None


def test_metric_row_with_date() -> None:
    r = MetricRow(
        source=MetricSource.SEARCH_CONSOLE,
        event_date=date(2026, 5, 1),
        metric_name="clicks",
        value=40.0,
    )
    assert r.event_date == date(2026, 5, 1)


def test_metric_row_negative_value_allowed() -> None:
    """Some metrics legitimately go negative (delta vs baseline)."""
    r = MetricRow(source=MetricSource.MANUAL, metric_name="delta", value=-5.0)
    assert r.value == -5.0


def test_metric_row_oversize_query_rejected() -> None:
    with pytest.raises(ValidationError):
        MetricRow(
            source=MetricSource.SEARCH_CONSOLE,
            metric_name="impressions",
            value=1.0,
            query="x" * 500,
        )


# ---------- MetricsSnapshot ----------

def _snapshot(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "rows": [],
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


def test_snapshot_minimal_validates() -> None:
    s = MetricsSnapshot.model_validate(_snapshot())
    assert s.contract_version == METRICS_SNAPSHOT_VERSION
    assert s.total_rows == 0


def test_snapshot_round_trip() -> None:
    s = MetricsSnapshot.model_validate(_snapshot())
    reloaded = MetricsSnapshot.from_json(s.to_json())
    assert reloaded.model_dump() == s.model_dump()


def test_snapshot_naive_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        MetricsSnapshot.model_validate(_snapshot(created_at="2026-06-01T12:00:00"))


def test_snapshot_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        MetricsSnapshot.model_validate(_snapshot(client_slug="Bad Slug"))


def test_snapshot_rows_by_source_filter() -> None:
    rows = [
        MetricRow(source=MetricSource.GA4, metric_name="x", value=1.0).model_dump(mode="json"),
        MetricRow(source=MetricSource.SOCIAL, metric_name="x", value=2.0).model_dump(mode="json"),
        MetricRow(source=MetricSource.GA4, metric_name="x", value=3.0).model_dump(mode="json"),
    ]
    s = MetricsSnapshot.model_validate(_snapshot(rows=rows))
    assert len(s.rows_by_source(MetricSource.GA4)) == 2
    assert len(s.rows_by_source(MetricSource.SOCIAL)) == 1


# ---------- AnalyticsImportReport ----------

def test_import_report_minimal() -> None:
    r = AnalyticsImportReport(
        client_slug="acme-saas",
        source=MetricSource.MANUAL,
        file_path="/tmp/foo.csv",
        rows_imported=10,
        rows_rejected=0,
        imported_at=_now(),
    )
    assert r.contract_version == ANALYTICS_IMPORT_REPORT_VERSION


def test_import_report_negative_counts_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsImportReport(
            client_slug="acme-saas",
            source=MetricSource.MANUAL,
            file_path="/tmp/foo.csv",
            rows_imported=-1,
            rows_rejected=0,
            imported_at=_now(),
        )


# ---------- Recommendation + Pack ----------

def test_recommendation_minimal() -> None:
    r = Recommendation(
        kind=RecommendationKind.REPEAT,
        priority=RecommendationPriority.HIGH,
        title="repeat winning channel",
        rationale="r",
        suggested_action="do this",
    )
    assert r.kind is RecommendationKind.REPEAT


def test_recommendation_pack_minimal() -> None:
    p = OptimizationRecommendationPack(
        client_slug="acme-saas",
        snapshot_id="s1",
        snapshot_contract_version="metrics-snapshot.v1",
        total_rows_analyzed=10,
        created_at=_now(),
    )
    assert p.contract_version == OPTIMIZATION_RECOMMENDATION_PACK_VERSION


def test_recommendation_pack_round_trip() -> None:
    p = OptimizationRecommendationPack(
        client_slug="acme-saas",
        snapshot_id="s1",
        snapshot_contract_version="metrics-snapshot.v1",
        total_rows_analyzed=10,
        channels=[ChannelPerformanceSummary(channel="linkedin", sample_rows=3)],
        seo_opportunities=SEOOpportunityReport(
            opportunities=[
                SEOOpportunity(
                    impressions=100, clicks=2, opportunity_score=10,
                    reason="low CTR",
                )
            ]
        ),
        created_at=_now(),
    )
    reloaded = OptimizationRecommendationPack.from_json(p.to_json())
    assert reloaded.model_dump() == p.model_dump()


def test_seo_opportunity_ctr_bounds() -> None:
    with pytest.raises(ValidationError):
        SEOOpportunity(
            impressions=10, clicks=0, ctr=2.0, opportunity_score=1, reason="x",
        )


def test_pack_naive_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        OptimizationRecommendationPack(
            client_slug="acme-saas",
            snapshot_id="s1",
            snapshot_contract_version="metrics-snapshot.v1",
            total_rows_analyzed=0,
            created_at=datetime(2026, 6, 1, 12, 0),
        )


# ---------- Privacy: no credential / URL fields ----------

def test_models_have_no_credential_fields() -> None:
    for cls in (
        MetricRow, MetricsSnapshot, AnalyticsImportReport,
        OptimizationRecommendationPack, Recommendation,
    ):
        fields = set(cls.model_fields.keys())
        for forbidden in ("token", "api_key", "secret", "credential", "url", "webhook_url"):
            assert forbidden not in fields, (
                f"{cls.__name__}.{forbidden} would be a leak vector"
            )
