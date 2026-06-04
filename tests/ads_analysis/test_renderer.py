"""Tests for the Google Ads insight pack Markdown renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from core.ads_analysis import (
    AdGroupProfile,
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
    render_markdown_ads_insights,
)


def _make_pack(**overrides) -> GoogleAdsInsightPack:
    insights = overrides.pop("insights", [])
    profiles = overrides.pop("profiles", [])
    stats = AdsInsightStats(
        total_insights=len(insights),
        by_severity={"high": sum(
            1 for i in insights if i.severity is AdsInsightSeverity.HIGH
        )},
        by_kind={},
        by_action={},
        ad_groups_profiled=len(profiles),
        rows_analyzed=overrides.pop("rows_analyzed", 0),
    )
    return GoogleAdsInsightPack(
        client_slug="acme",
        snapshot_id="snap-1",
        snapshot_contract_version="metrics-snapshot.v1",
        profiles=profiles,
        insights=insights,
        stats=stats,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
        rule_set_id="ads-analyzer.v1",
    )


def test_render_empty_pack() -> None:
    md = render_markdown_ads_insights(_make_pack())
    assert "Google Ads Insight Pack" in md
    assert "No insights triggered" in md
    assert "Read-only" in md


def test_render_includes_severity_and_action() -> None:
    insight = GoogleAdsInsight(
        kind=AdsInsightKind.HIGH_SPEND_ZERO_CONV,
        severity=AdsInsightSeverity.HIGH,
        suggested_action=AdsInsightAction.PAUSE_CANDIDATE,
        title="High spend zero conv — Brand / X",
        rationale="Spent $120 with 0 conversions.",
        evidence={"cost": 120.0, "conversions": 0.0},
        thresholds_used={"min_cost": 50.0},
    )
    md = render_markdown_ads_insights(_make_pack(insights=[insight]))
    assert "[HIGH] High spend zero conv" in md
    assert "pause_candidate" in md
    assert "Evidence" in md
    assert "Thresholds" in md


def test_render_profiles_table() -> None:
    profile = AdGroupProfile(
        content_ref="campaign:1::ad_group:100",
        campaign_id="1", ad_group_id="100",
        dimension="Brand / X", sample_rows=5,
        impressions=1000, clicks=50, cost=25.0,
        conversions=3, conversions_value=150.0,
        ctr=0.05, cpc=0.5, cpa=8.33, conversion_rate=0.06,
    )
    md = render_markdown_ads_insights(_make_pack(profiles=[profile]))
    assert "Ad group profiles" in md
    assert "Brand / X" in md


def test_render_renderer_is_pure() -> None:
    """Two calls on the same pack produce byte-identical output."""
    insight = GoogleAdsInsight(
        kind=AdsInsightKind.LOW_CTR_HIGH_IMPR,
        severity=AdsInsightSeverity.MEDIUM,
        suggested_action=AdsInsightAction.IMPROVE_AD_COPY,
        title="t", rationale="r",
        evidence={"a": 1.0, "b": 2.0},
        thresholds_used={"x": 1.0, "y": 2.0},
    )
    pack = _make_pack(insights=[insight])
    assert render_markdown_ads_insights(pack) == render_markdown_ads_insights(pack)
