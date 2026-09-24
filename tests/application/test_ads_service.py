"""Tests for the Google Ads analysis + feedback-bridge application
services (architecture/application-service-boundary, batch 3)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from core.ads_analysis import (
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)
from core.ads_analysis.models import GOOGLE_ADS_INSIGHT_PACK_KIND
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)
from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.ads import analyze_ads, build_ads_feedback
from core.memory import JsonFileMemory


def _ctx(tmp_path: Path, client: str = "acme") -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )


def _seed_snapshot(root: Path, *, client: str = "acme") -> None:
    mem = JsonFileMemory(root)
    now = datetime(2026, 6, 4, tzinfo=UTC)
    rows = [
        MetricRow(
            source=MetricSource.GOOGLE_ADS,
            event_date=date(2026, 5, 15),
            channel="google_ads",
            content_ref="campaign:1::ad_group:100",
            dimension="Brand / Wasteful",
            metric_name=metric,
            value=value,
        )
        for metric, value in (
            ("impressions", 2000.0), ("clicks", 80.0),
            ("cost", 120.0), ("conversions", 0.0),
            ("conversions_value", 0.0),
        )
    ]
    snap = MetricsSnapshot(client_slug=client, rows=rows, created_at=now, updated_at=now)
    mem.put(client, METRICS_SNAPSHOT_KIND, SINGLETON_ID, snap.model_dump(mode="json"))


def _seed_insight_pack(root: Path, *, client: str = "acme") -> None:
    mem = JsonFileMemory(root)
    insight = GoogleAdsInsight(
        kind=AdsInsightKind.HIGH_SPEND_ZERO_CONV,
        severity=AdsInsightSeverity.HIGH,
        suggested_action=AdsInsightAction.PAUSE_CANDIDATE,
        title="High spend zero conv",
        rationale="Spent $120 with 0 conversions.",
        content_ref="campaign:42::ad_group:100",
        campaign_id="42",
        ad_group_id="100",
        dimension="Brand / Wasteful",
        evidence={"cost": 120.0, "conversions": 0.0},
        thresholds_used={"min_cost": 50.0},
    )
    pack = GoogleAdsInsightPack(
        client_slug=client,
        snapshot_id="snap-1",
        snapshot_contract_version="metrics-snapshot.v1",
        profiles=[],
        insights=[insight],
        stats=AdsInsightStats(
            total_insights=1,
            by_severity={"high": 1},
            by_kind={"high_spend_zero_conv": 1},
            by_action={"pause_candidate": 1},
            ad_groups_profiled=1,
            rows_analyzed=4,
        ),
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
        rule_set_id="ads-analyzer.v1",
    )
    mem.put(client, GOOGLE_ADS_INSIGHT_PACK_KIND, "current", pack.model_dump(mode="json"))


# ---------- analyze_ads: happy path ----------

def test_analyze_ads_valid_snapshot_succeeds(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    result = analyze_ads(ctx)
    assert result.ok
    assert result.data.client_slug == "acme"
    assert result.data.stats.rows_analyzed == 5
    assert len(result.artifacts) == 2


def test_analyze_ads_writes_md_and_json(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    analyze_ads(ctx)
    md_path = tmp_path / "out" / "google-ads-insight-pack.md"
    json_path = tmp_path / "out" / "google-ads-insight-pack.json"
    assert md_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["client_slug"] == "acme"


def test_analyze_ads_persists_and_audits(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    analyze_ads(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists("acme", "google_ads_insight_pack", "current")
    events = mem.read_audit_events("acme")
    analyzed = [e for e in events if "google_ads_insight_pack" in e.payload]
    assert len(analyzed) == 1
    assert analyzed[0].payload["google_ads_insight_pack"]["action"] == "analyzed"


# ---------- analyze_ads: no invented metrics ----------

def test_analyze_ads_no_evidence_no_roas_no_lift_fields(tmp_path: Path) -> None:
    """Every numeric field the pack reports must trace back to the
    seeded rows — this is a structural smoke check that nothing was
    fabricated (a real 'invented metric' regression would add unknown
    keys like roas/conversion_lift/revenue_impact to the JSON output)."""
    _seed_snapshot(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    result = analyze_ads(ctx)
    blob = result.data.to_json().lower()
    for forbidden in ("roas", "conversion_lift", "revenue_impact", "ctr_lift"):
        assert forbidden not in blob
    # profiles/insights are entirely derived from the 5 seeded rows.
    assert result.data.stats.rows_analyzed == 5


# ---------- analyze_ads: error mapping ----------

def test_analyze_ads_missing_snapshot_returns_not_found(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "ghost")
    result = analyze_ads(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND
    assert "MetricsSnapshot" in result.error.message


# ---------- analyze_ads: tenant isolation ----------

def test_analyze_ads_two_clients_do_not_cross_contaminate(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path / "mem", client="acme")
    ctx_b = _ctx(tmp_path, "other-client")
    result_b = analyze_ads(ctx_b)
    assert not result_b.ok
    assert result_b.error.code is ErrorCode.NOT_FOUND


# ---------- build_ads_feedback: happy path ----------

def test_build_ads_feedback_valid_insight_pack_succeeds(tmp_path: Path) -> None:
    _seed_insight_pack(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    result = build_ads_feedback(ctx)
    assert result.ok
    assert result.data.client_slug == "acme"
    assert result.data.stats.total_recommendations == 1
    assert len(result.artifacts) == 2


def test_build_ads_feedback_writes_md_and_json(tmp_path: Path) -> None:
    _seed_insight_pack(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    build_ads_feedback(ctx)
    md_path = tmp_path / "out" / "ads-feedback-bridge-pack.md"
    json_path = tmp_path / "out" / "ads-feedback-bridge-pack.json"
    assert md_path.exists()
    assert json_path.exists()


def test_build_ads_feedback_persists_and_audits(tmp_path: Path) -> None:
    _seed_insight_pack(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    build_ads_feedback(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists("acme", "ads_feedback_bridge_pack", "current")
    events = mem.read_audit_events("acme")
    bridged = [e for e in events if "ads_feedback_bridge_pack" in e.payload]
    assert len(bridged) == 1
    assert bridged[0].payload["ads_feedback_bridge_pack"]["action"] == "bridged"


# ---------- build_ads_feedback: no unsupported numeric claims ----------

def test_build_ads_feedback_optional_cross_refs_default_to_none(tmp_path: Path) -> None:
    """With no CampaignFeedbackPack/ExecutionTaskPack/IterationPlan
    persisted, the bridge must report None for each — never guess or
    fabricate a linkage."""
    _seed_insight_pack(tmp_path / "mem")
    ctx = _ctx(tmp_path)
    result = build_ads_feedback(ctx)
    assert result.data.feedback_pack_id is None
    assert result.data.execution_task_pack_id is None
    assert result.data.iteration_plan_id is None


# ---------- build_ads_feedback: error mapping ----------

def test_build_ads_feedback_missing_insight_pack_returns_not_found(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "ghost")
    result = build_ads_feedback(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND
    assert "GoogleAdsInsightPack" in result.error.message


# ---------- build_ads_feedback: tenant isolation ----------

def test_build_ads_feedback_two_clients_do_not_cross_contaminate(tmp_path: Path) -> None:
    _seed_insight_pack(tmp_path / "mem", client="acme")
    ctx_b = _ctx(tmp_path, "other-client")
    result_b = build_ads_feedback(ctx_b)
    assert not result_b.ok
    assert result_b.error.code is ErrorCode.NOT_FOUND
