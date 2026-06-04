"""Tests for the ads feedback bridge — insight → recommendation flow."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.ads_analysis import (
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)
from core.ads_analysis.models import GOOGLE_ADS_INSIGHT_PACK_KIND
from core.ads_feedback import (
    ADS_FEEDBACK_BRIDGE_PACK_KIND,
    AdsAdjustmentKind,
    AdsFeedbackBridge,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    bridge_and_persist,
)
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)
from core.memory import JsonFileMemory


def _make_insight(
    kind: AdsInsightKind,
    *,
    action: AdsInsightAction,
    severity: AdsInsightSeverity = AdsInsightSeverity.HIGH,
    campaign_id: str = "42",
    ad_group_id: str | None = "100",
    dimension: str = "Brand / Wasteful",
) -> GoogleAdsInsight:
    return GoogleAdsInsight(
        kind=kind,
        severity=severity,
        suggested_action=action,
        title=f"Insight {kind.value}",
        rationale="Auto rationale",
        content_ref=(
            f"campaign:{campaign_id}::ad_group:{ad_group_id}"
            if ad_group_id else f"campaign:{campaign_id}"
        ),
        campaign_id=campaign_id,
        ad_group_id=ad_group_id,
        dimension=dimension,
        evidence={"cost": 100.0},
        thresholds_used={"min_cost": 50.0},
    )


def _persist_insight_pack(
    mem: JsonFileMemory,
    *,
    client: str,
    insights: list[GoogleAdsInsight],
) -> GoogleAdsInsightPack:
    stats = AdsInsightStats(
        total_insights=len(insights),
        by_severity={}, by_kind={}, by_action={},
        ad_groups_profiled=len(insights),
        rows_analyzed=0,
    )
    pack = GoogleAdsInsightPack(
        client_slug=client,
        snapshot_id="snap-1",
        snapshot_contract_version="metrics-snapshot.v1",
        profiles=[],
        insights=insights,
        stats=stats,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
        rule_set_id="ads-analyzer.v1",
    )
    mem.put(client, GOOGLE_ADS_INSIGHT_PACK_KIND, "current",
            pack.model_dump(mode="json"))
    return pack


# ---------- raises when no insight pack ----------


def test_bridge_raises_when_no_insight_pack(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError, match="no GoogleAdsInsightPack"):
        AdsFeedbackBridge(mem).build("acme")


# ---------- insight kind → recommendation kind ----------


def test_pause_candidate_becomes_pause_review(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert len(pack.recommendations) == 1
    assert pack.recommendations[0].kind is AdsRecommendationKind.PAUSE_REVIEW
    assert pack.recommendations[0].priority is AdsRecommendationPriority.HIGH
    # Adjustment created for the campaign.
    assert len(pack.campaign_adjustments) == 1
    assert pack.campaign_adjustments[0].kind is AdsAdjustmentKind.PAUSE_REVIEW
    assert pack.campaign_adjustments[0].campaign_id == "42"


def test_scale_candidate_becomes_scale_opportunity(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.SCALE_CANDIDATE,
            action=AdsInsightAction.SCALE_CANDIDATE,
            severity=AdsInsightSeverity.MEDIUM,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.recommendations[0].kind is AdsRecommendationKind.SCALE_OPPORTUNITY
    assert pack.campaign_adjustments[0].kind is AdsAdjustmentKind.SCALE_REVIEW


def test_low_ctr_becomes_improve_ad_copy(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.LOW_CTR_HIGH_IMPR,
            action=AdsInsightAction.IMPROVE_AD_COPY,
            severity=AdsInsightSeverity.MEDIUM,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.recommendations[0].kind is AdsRecommendationKind.IMPROVE_AD_COPY
    # IMPROVE_AD_COPY does NOT generate a campaign adjustment.
    assert pack.campaign_adjustments == []


def test_good_ctr_low_conv_becomes_review_landing(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.GOOD_CTR_LOW_CONV_RATE,
            action=AdsInsightAction.REVIEW_LANDING,
            severity=AdsInsightSeverity.MEDIUM,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.recommendations[0].kind is AdsRecommendationKind.REVIEW_LANDING


def test_review_campaign_creates_optimize_adjustment(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_LOW_CONV,
            action=AdsInsightAction.REVIEW_CAMPAIGN,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.campaign_adjustments[0].kind is AdsAdjustmentKind.OPTIMIZE_REVIEW


def test_budget_review_becomes_reallocate_adjustment(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.BUDGET_REVIEW,
            action=AdsInsightAction.BUDGET_REVIEW,
            severity=AdsInsightSeverity.LOW,
            ad_group_id=None,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.recommendations[0].kind is AdsRecommendationKind.BUDGET_REVIEW
    assert pack.campaign_adjustments[0].kind is AdsAdjustmentKind.REALLOCATE_REVIEW


# ---------- task generation ----------


def test_each_recommendation_produces_a_task_plus_review_task(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        ),
        _make_insight(
            AdsInsightKind.LOW_CTR_HIGH_IMPR,
            action=AdsInsightAction.IMPROVE_AD_COPY,
            severity=AdsInsightSeverity.MEDIUM,
            campaign_id="43",
        ),
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    # 2 recs + 1 trailing measurement task
    assert pack.stats.total_suggested_tasks == 3
    categories = [t.category for t in pack.suggested_tasks]
    assert "optimization" in categories
    assert "content" in categories
    assert categories[-1] == "measurement"


def test_empty_insight_pack_produces_no_tasks(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.suggested_tasks == []
    assert pack.recommendations == []
    assert "empty" in (pack.executive_summary or "").lower()


# ---------- adjustment dedup ----------


def test_multiple_insights_same_campaign_dedup_adjustment(tmp_path: Path) -> None:
    """Two pause-candidate insights on the same campaign should
    produce one adjustment (campaign-level) but two recommendations
    (ad-group-level)."""
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
            ad_group_id="100",
        ),
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
            ad_group_id="200",
        ),
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert len(pack.recommendations) == 2
    assert len(pack.campaign_adjustments) == 1


# ---------- cross-refs ----------


def test_cross_refs_populated_when_packs_exist(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        )
    ])
    mem.put("acme", "campaign_feedback_pack", "current", {"pack_id": "fb-1"})
    mem.put("acme", "campaign_execution_task_pack", "current", {"pack_id": "etp-1"})
    mem.put("acme", "next_campaign_iteration_plan", "current", {"plan_id": "plan-1"})
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.feedback_pack_id == "fb-1"
    assert pack.execution_task_pack_id == "etp-1"
    assert pack.iteration_plan_id == "plan-1"


def test_cross_refs_none_when_packs_missing(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        )
    ])
    pack = AdsFeedbackBridge(mem).build("acme")
    assert pack.feedback_pack_id is None
    assert pack.execution_task_pack_id is None
    assert pack.iteration_plan_id is None


# ---------- persistence + audit ----------


def test_bridge_and_persist_writes_pack_and_audit(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        )
    ])
    pack = bridge_and_persist(mem, client_slug="acme")
    raw = mem.get("acme", ADS_FEEDBACK_BRIDGE_PACK_KIND, "current")
    assert raw["pack_id"] == pack.pack_id

    events = list(mem.read_audit_events("acme"))
    actions = [
        e.payload["ads_feedback_bridge_pack"]["action"]
        for e in events if "ads_feedback_bridge_pack" in e.payload
    ]
    assert "bridged" in actions


# ---------- read-only guarantees ----------


def test_bridge_does_not_mutate_upstream_packs(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    insight_pack = _persist_insight_pack(mem, client="acme", insights=[
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        )
    ])
    now = datetime(2026, 6, 4, tzinfo=UTC)
    snap = MetricsSnapshot(
        client_slug="acme", rows=[
            MetricRow(
                source=MetricSource.GOOGLE_ADS,
                event_date=date(2026, 5, 15),
                channel="google_ads",
                content_ref="campaign:42::ad_group:100",
                metric_name="impressions",
                value=1000,
            ),
        ],
        created_at=now, updated_at=now,
    )
    mem.put("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID,
            snap.model_dump(mode="json"))

    insight_before = mem.get("acme", GOOGLE_ADS_INSIGHT_PACK_KIND, "current")
    snap_before = mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)
    AdsFeedbackBridge(mem).build("acme")
    insight_after = mem.get("acme", GOOGLE_ADS_INSIGHT_PACK_KIND, "current")
    snap_after = mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)
    assert insight_before == insight_after
    assert snap_before == snap_after
    _ = insight_pack  # silence unused


def test_no_google_ads_sdk_reference_in_bridge_source() -> None:
    """Pin: the bridge module must not reference the Google Ads SDK
    or any mutation method."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "core" / "ads_feedback"
    forbidden = (
        "google.ads", "googleads", "GoogleAdsClient",
        "mutate_campaigns", "mutate_ad_groups", "mutate_ads",
        "CampaignOperation", "AdGroupOperation",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} references {needle!r}"


def test_deterministic_recommendation_ordering(tmp_path: Path) -> None:
    """Same insight pack → same recommendation order."""
    mem_a = JsonFileMemory(tmp_path / "a")
    mem_b = JsonFileMemory(tmp_path / "b")
    insights = [
        _make_insight(
            AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            action=AdsInsightAction.PAUSE_CANDIDATE,
        ),
        _make_insight(
            AdsInsightKind.SCALE_CANDIDATE,
            action=AdsInsightAction.SCALE_CANDIDATE,
            severity=AdsInsightSeverity.MEDIUM,
            campaign_id="43",
        ),
    ]
    _persist_insight_pack(mem_a, client="acme", insights=insights)
    _persist_insight_pack(mem_b, client="acme", insights=insights)
    a = AdsFeedbackBridge(mem_a).build("acme")
    b = AdsFeedbackBridge(mem_b).build("acme")
    a_kinds = [r.kind.value for r in a.recommendations]
    b_kinds = [r.kind.value for r in b.recommendations]
    assert a_kinds == b_kinds
