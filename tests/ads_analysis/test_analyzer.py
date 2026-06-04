"""Tests for the Google Ads analyzer — rule-by-rule + integration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.ads_analysis import (
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    GoogleAdsAnalyzer,
    analyze_and_persist_ads,
)
from core.ads_analysis.analyzer import (
    _aggregate_profiles,
    _apply_rules,
)
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)
from core.memory import JsonFileMemory


def _row(metric: str, value: float, *, content_ref: str,
         dimension: str | None = None) -> MetricRow:
    return MetricRow(
        source=MetricSource.GOOGLE_ADS,
        event_date=date(2026, 5, 15),
        channel="google_ads",
        content_ref=content_ref,
        metric_name=metric,
        value=value,
        dimension=dimension,
    )


def _ad_group_rows(
    content_ref: str,
    *,
    impressions: float, clicks: float, cost: float, conversions: float,
    conversions_value: float = 0.0,
    dimension: str | None = None,
) -> list[MetricRow]:
    return [
        _row("impressions", impressions, content_ref=content_ref, dimension=dimension),
        _row("clicks", clicks, content_ref=content_ref, dimension=dimension),
        _row("cost", cost, content_ref=content_ref, dimension=dimension),
        _row("conversions", conversions, content_ref=content_ref, dimension=dimension),
        _row("conversions_value", conversions_value, content_ref=content_ref, dimension=dimension),
    ]


def _persist_snapshot(mem: JsonFileMemory, *, client: str,
                      rows: list[MetricRow]) -> MetricsSnapshot:
    now = datetime(2026, 6, 4, tzinfo=UTC)
    snap = MetricsSnapshot(
        client_slug=client, rows=rows, created_at=now, updated_at=now,
    )
    mem.put(client, METRICS_SNAPSHOT_KIND, SINGLETON_ID,
            snap.model_dump(mode="json"))
    return snap


# ---------- aggregation ----------


def test_aggregate_profiles_sums_per_content_ref() -> None:
    rows = (
        _ad_group_rows("campaign:1::ad_group:100",
                       impressions=500, clicks=20, cost=10.0,
                       conversions=1.0)
        + _ad_group_rows("campaign:1::ad_group:100",
                         impressions=500, clicks=20, cost=10.0,
                         conversions=1.0)
        + _ad_group_rows("campaign:1::ad_group:200",
                        impressions=100, clicks=5, cost=2.5,
                        conversions=0.0)
    )
    profiles = _aggregate_profiles(rows)
    assert len(profiles) == 2
    by_ref = {p.content_ref: p for p in profiles}
    a = by_ref["campaign:1::ad_group:100"]
    assert a.impressions == 1000
    assert a.clicks == 40
    assert a.cost == 20.0
    assert a.conversions == 2.0
    assert a.ctr == pytest.approx(40 / 1000)
    assert a.cpc == pytest.approx(20 / 40)
    assert a.cpa == pytest.approx(20 / 2)
    assert a.conversion_rate == pytest.approx(2 / 40)
    assert a.campaign_id == "1"
    assert a.ad_group_id == "100"


def test_aggregate_handles_zero_clicks_and_zero_conversions() -> None:
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=100, clicks=0, cost=5.0, conversions=0.0)
    profiles = _aggregate_profiles(rows)
    p = profiles[0]
    assert p.ctr == pytest.approx(0.0)
    assert p.cpc is None
    assert p.cpa is None
    assert p.conversion_rate is None


# ---------- per-rule unit tests ----------


def test_rule_high_spend_zero_conv() -> None:
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=2000, clicks=80, cost=120.0, conversions=0.0,
                          dimension="Brand / Wasteful")
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    kinds = {i.kind for i in insights}
    assert AdsInsightKind.HIGH_SPEND_ZERO_CONV in kinds
    matching = [i for i in insights if i.kind is AdsInsightKind.HIGH_SPEND_ZERO_CONV]
    assert matching[0].severity is AdsInsightSeverity.HIGH
    assert matching[0].suggested_action is AdsInsightAction.PAUSE_CANDIDATE


def test_rule_high_spend_low_conv() -> None:
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=2000, clicks=80, cost=150.0, conversions=1.0)
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    assert any(i.kind is AdsInsightKind.HIGH_SPEND_LOW_CONV for i in insights)
    matching = [i for i in insights if i.kind is AdsInsightKind.HIGH_SPEND_LOW_CONV][0]
    assert matching.severity is AdsInsightSeverity.HIGH
    assert matching.suggested_action is AdsInsightAction.REVIEW_CAMPAIGN


def test_rule_low_ctr_high_impressions() -> None:
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=5000, clicks=20, cost=15.0, conversions=1.0)
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    assert any(i.kind is AdsInsightKind.LOW_CTR_HIGH_IMPR for i in insights)
    matching = [i for i in insights if i.kind is AdsInsightKind.LOW_CTR_HIGH_IMPR][0]
    assert matching.suggested_action is AdsInsightAction.IMPROVE_AD_COPY


def test_rule_good_ctr_low_conv_rate() -> None:
    # CTR = 100/1000 = 0.10 (good), conversions=0 → conv_rate=0 < 0.01
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=1000, clicks=100, cost=20.0, conversions=0.0)
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    # Rule 4 needs conversion_rate < 0.01 but rule 1 also fires
    # (cost=20<50 → no rule 1). Tweak: bump cost to test rule 1 doesn't.
    # cost=20 < 50 so high_spend_zero_conv does NOT fire, good.
    assert any(
        i.kind is AdsInsightKind.GOOD_CTR_LOW_CONV_RATE for i in insights
    )
    matching = [
        i for i in insights
        if i.kind is AdsInsightKind.GOOD_CTR_LOW_CONV_RATE
    ][0]
    assert matching.suggested_action is AdsInsightAction.REVIEW_LANDING


def test_rule_high_cpa_outlier() -> None:
    # Build 3 ad groups; one has CPA way above median.
    rows: list[MetricRow] = []
    rows += _ad_group_rows("campaign:1::ad_group:100",
                           impressions=1000, clicks=50, cost=10.0, conversions=5.0)
    rows += _ad_group_rows("campaign:1::ad_group:200",
                           impressions=1000, clicks=50, cost=12.0, conversions=4.0)
    # Outlier: CPA = 20.0
    rows += _ad_group_rows("campaign:1::ad_group:300",
                           impressions=1000, clicks=50, cost=20.0, conversions=1.0)
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    outliers = [i for i in insights if i.kind is AdsInsightKind.HIGH_CPA_OUTLIER]
    assert outliers
    assert outliers[0].suggested_action is AdsInsightAction.REVIEW_AD_GROUP


def test_rule_scale_candidate() -> None:
    # Median CPA across snapshot, plus a low-CPA efficient ad group.
    rows: list[MetricRow] = []
    rows += _ad_group_rows("campaign:1::ad_group:100",
                           impressions=1000, clicks=50, cost=20.0, conversions=2.0)
    rows += _ad_group_rows("campaign:1::ad_group:200",
                           impressions=1000, clicks=50, cost=24.0, conversions=2.0)
    # Scale candidate: CPA = 5/5 = 1.0 (way below median ~10)
    rows += _ad_group_rows("campaign:1::ad_group:300",
                           impressions=1000, clicks=50, cost=5.0, conversions=5.0)
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    scale = [i for i in insights if i.kind is AdsInsightKind.SCALE_CANDIDATE]
    assert scale
    assert scale[0].suggested_action is AdsInsightAction.SCALE_CANDIDATE


def test_rule_budget_review_top_quartile() -> None:
    # 4 campaigns; the highest-spend one should trigger budget_review.
    rows: list[MetricRow] = []
    rows += _ad_group_rows("campaign:1::ad_group:100",
                           impressions=1000, clicks=10, cost=10.0, conversions=1.0)
    rows += _ad_group_rows("campaign:2::ad_group:100",
                           impressions=1000, clicks=10, cost=20.0, conversions=1.0)
    rows += _ad_group_rows("campaign:3::ad_group:100",
                           impressions=1000, clicks=10, cost=30.0, conversions=1.0)
    rows += _ad_group_rows("campaign:4::ad_group:100",
                           impressions=1000, clicks=10, cost=200.0, conversions=1.0)
    profiles = _aggregate_profiles(rows)
    insights = _apply_rules(profiles)
    budget = [i for i in insights if i.kind is AdsInsightKind.BUDGET_REVIEW]
    assert budget
    # Top-quartile cutoff includes campaign 4 (and may include 3).
    campaign_ids = {i.campaign_id for i in budget}
    assert "4" in campaign_ids


def test_no_insights_when_no_ads_rows(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_snapshot(mem, client="acme", rows=[])
    pack = GoogleAdsAnalyzer(mem).analyze("acme")
    assert pack.stats.total_insights == 0
    assert pack.stats.ad_groups_profiled == 0


# ---------- integration: analyzer + memory + audit ----------


def test_analyze_and_persist_writes_pack_and_audit(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=2000, clicks=80, cost=120.0,
                          conversions=0.0, dimension="Brand / Wasteful")
    _persist_snapshot(mem, client="acme", rows=rows)
    pack = analyze_and_persist_ads(mem, client_slug="acme")
    assert pack.stats.total_insights >= 1

    # Pack is persisted.
    from core.ads_analysis.models import GOOGLE_ADS_INSIGHT_PACK_KIND
    raw = mem.get("acme", GOOGLE_ADS_INSIGHT_PACK_KIND, "current")
    assert raw["pack_id"] == pack.pack_id

    # Audit event recorded.
    events = list(mem.read_audit_events("acme"))
    assert any(
        "google_ads_insight_pack" in e.payload
        and e.payload["google_ads_insight_pack"]["action"] == "analyzed"
        for e in events
    )


def test_analyze_raises_when_no_snapshot(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError, match="no MetricsSnapshot"):
        GoogleAdsAnalyzer(mem).analyze("acme")


def test_deterministic_insight_ordering(tmp_path: Path) -> None:
    """Same inputs (modulo new ids) → same severity / kind ordering."""
    mem_a = JsonFileMemory(tmp_path / "a")
    mem_b = JsonFileMemory(tmp_path / "b")
    rows: list[MetricRow] = []
    rows += _ad_group_rows("campaign:1::ad_group:100",
                           impressions=2000, clicks=80, cost=120.0,
                           conversions=0.0)
    rows += _ad_group_rows("campaign:2::ad_group:200",
                           impressions=5000, clicks=20, cost=15.0,
                           conversions=1.0)
    rows += _ad_group_rows("campaign:3::ad_group:300",
                           impressions=1000, clicks=50, cost=5.0,
                           conversions=5.0)
    _persist_snapshot(mem_a, client="acme", rows=rows)
    _persist_snapshot(mem_b, client="acme", rows=rows)
    a = GoogleAdsAnalyzer(mem_a).analyze("acme")
    b = GoogleAdsAnalyzer(mem_b).analyze("acme")
    a_order = [(i.severity.value, i.kind.value, i.content_ref) for i in a.insights]
    b_order = [(i.severity.value, i.kind.value, i.content_ref) for i in b.insights]
    assert a_order == b_order


def test_pack_does_not_mutate_snapshot(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    rows = _ad_group_rows("campaign:1::ad_group:100",
                          impressions=2000, clicks=80, cost=120.0,
                          conversions=0.0)
    _persist_snapshot(mem, client="acme", rows=rows)
    snap_before = mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)
    GoogleAdsAnalyzer(mem).analyze("acme")
    snap_after = mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)
    assert snap_before == snap_after


def test_no_mutation_method_in_analyzer_source() -> None:
    """Pin: the analyzer module references no Google Ads mutation
    method name (it should be impossible — it only reads from
    Memory — but pinned for posterity)."""
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / "core" / "ads_analysis"
    forbidden = (
        "mutate_campaigns", "mutate_ad_groups", "mutate_ads",
        "mutate_campaign_budgets", "CampaignOperation",
        "AdGroupOperation", "GoogleAdsClient",
    )
    for py in path.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} references {needle!r}"
