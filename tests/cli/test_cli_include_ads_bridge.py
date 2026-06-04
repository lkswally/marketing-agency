"""CLI integration tests for the MKT-6H ``--include-ads-bridge`` flag
across ``feedback-plan``, ``build-tasks`` and ``apply-feedback``."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from cli.main import main
from core.ads_feedback.models import (
    ADS_FEEDBACK_BRIDGE_PACK_KIND,
    AdsAdjustmentKind,
    AdsBridgeStats,
    AdsCampaignAdjustment,
    AdsFeedbackBridgePack,
    AdsRecommendation,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    AdsSuggestedTask,
)
from core.ads_feedback.models import SINGLETON_ID as ADS_BRIDGE_SINGLETON
from core.memory import JsonFileMemory


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _seed_ads_bridge_pack(root: Path, *, client: str = "acme") -> str:
    mem = JsonFileMemory(root)
    rec = AdsRecommendation(
        kind=AdsRecommendationKind.PAUSE_REVIEW,
        priority=AdsRecommendationPriority.HIGH,
        title="Pause Brand Wasteful",
        rationale="High spend zero conv.",
        suggested_action="Review for pause.",
        campaign_id="42", ad_group_id="100",
        content_ref="campaign:42::ad_group:100",
        dimension="Brand / Wasteful",
    )
    adj = AdsCampaignAdjustment(
        campaign_id="42",
        dimension="Brand",
        kind=AdsAdjustmentKind.PAUSE_REVIEW,
        rationale="Insight flagged pause.",
        suggested_next_step="Manually pause in Ads UI.",
    )
    task = AdsSuggestedTask(
        title="Review pause candidate",
        category="optimization",
        priority=AdsRecommendationPriority.HIGH,
        rationale="r",
    )
    bridge = AdsFeedbackBridgePack(
        client_slug=client,
        insight_pack_id="insight-1",
        insight_pack_contract_version="google-ads-insight-pack.v1",
        recommendations=[rec],
        campaign_adjustments=[adj],
        keyword_proposals=[],
        suggested_tasks=[task],
        executive_summary="t",
        stats=AdsBridgeStats(
            total_recommendations=1,
            total_campaign_adjustments=1,
            total_keyword_proposals=0,
            total_suggested_tasks=1,
            insights_consumed=1,
        ),
        created_at=_now(),
        rule_set_id="ads-feedback-bridge.v1",
    )
    mem.put(client, ADS_FEEDBACK_BRIDGE_PACK_KIND, ADS_BRIDGE_SINGLETON,
            bridge.model_dump(mode="json"))
    return bridge.pack_id


# ============================================================
# build-tasks --include-ads-bridge
# ============================================================


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _prime_pipeline(tmp_path: Path) -> str:
    """Run the full campaign pipeline so the artifacts the
    build-tasks / feedback-plan / apply-feedback CLIs consume exist
    in memory."""
    code, stdout = _run([
        "run-campaign",
        "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    return payload["client_slug"]


def _seed_strategy_report(root: Path, *, client: str = "acme") -> str:
    """Drive the standard pipeline; ``client`` is ignored and
    the actual slug from the intake is returned."""
    return _prime_pipeline(root.parent)


def _run_build_tasks(
    tmp_path: Path, *, slug: str, include_flag: bool,
) -> dict:
    argv = [
        "build-tasks",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ]
    if include_flag:
        argv.append("--include-ads-bridge")
    code, stdout = _run(argv)
    assert code == 0, stdout
    return json.loads(stdout)


def test_build_tasks_without_flag_does_not_promote(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _seed_ads_bridge_pack(tmp_path / "mem", client=slug)
    payload = _run_build_tasks(tmp_path, slug=slug, include_flag=False)
    pack_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    for t in pack_raw["tasks"]:
        notes = (t.get("notes") or "")
        assert "ads_bridge" not in notes


def test_build_tasks_with_flag_promotes(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _seed_ads_bridge_pack(tmp_path / "mem", client=slug)
    payload = _run_build_tasks(tmp_path, slug=slug, include_flag=True)
    pack_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    promoted = [
        t for t in pack_raw["tasks"]
        if "ads_bridge" in (t.get("notes") or "")
    ]
    assert len(promoted) == 1
    assert promoted[0]["channel"] == "google_ads"


def test_build_tasks_with_flag_no_bridge_pack_is_noop(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    payload = _run_build_tasks(tmp_path, slug=slug, include_flag=True)
    pack_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    for t in pack_raw["tasks"]:
        notes = (t.get("notes") or "")
        assert "ads_bridge" not in notes


def test_build_tasks_with_flag_idempotent(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _seed_ads_bridge_pack(tmp_path / "mem", client=slug)
    payload = None
    for _ in range(2):
        payload = _run_build_tasks(tmp_path, slug=slug, include_flag=True)
    pack_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    promoted = [
        t for t in pack_raw["tasks"]
        if "ads_bridge" in (t.get("notes") or "")
    ]
    # Idempotent: should still be 1, not 2.
    assert len(promoted) == 1


# ============================================================
# feedback-plan --include-ads-bridge
# ============================================================


def _seed_optimization_recommendation_pack(
    root: Path, *, client: str = "acme",
) -> None:
    """Minimal pack to satisfy the feedback-plan pre-requisite."""
    from datetime import date

    from core.analytics.models import (
        METRICS_SNAPSHOT_KIND,
        OPTIMIZATION_RECOMMENDATION_PACK_KIND,
        ChannelPerformanceSummary,
        MetricRow,
        MetricSource,
        MetricsSnapshot,
        OptimizationRecommendationPack,
        SEOOpportunityReport,
    )
    from core.analytics.models import (
        SINGLETON_ID as ANL_SINGLETON,
    )

    mem = JsonFileMemory(root)
    snap = MetricsSnapshot(
        client_slug=client,
        rows=[
            MetricRow(
                source=MetricSource.GA4,
                event_date=date(2026, 5, 15),
                channel="organic_search",
                metric_name="sessions",
                value=100,
            )
        ],
        created_at=_now(),
        updated_at=_now(),
    )
    mem.put(client, METRICS_SNAPSHOT_KIND, ANL_SINGLETON,
            snap.model_dump(mode="json"))
    rec_pack = OptimizationRecommendationPack(
        client_slug=client,
        snapshot_id=snap.snapshot_id,
        snapshot_contract_version=snap.contract_version,
        total_rows_analyzed=1,
        channels=[ChannelPerformanceSummary(
            channel="organic_search", sample_rows=1,
        )],
        top_content=[],
        seo_opportunities=SEOOpportunityReport(opportunities=[]),
        recommendations=[],
        next_actions=[],
        created_at=_now(),
    )
    mem.put(client, OPTIMIZATION_RECOMMENDATION_PACK_KIND, ANL_SINGLETON,
            rec_pack.model_dump(mode="json"))


def test_feedback_plan_without_flag_does_not_promote(tmp_path: Path) -> None:
    _seed_optimization_recommendation_pack(tmp_path / "mem")
    _seed_ads_bridge_pack(tmp_path / "mem")
    code, stdout = _run([
        "feedback-plan",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    pack_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    for t in pack_raw["suggested_tasks"]:
        for ref in t.get("evidence_refs", []):
            assert "ads_bridge" not in ref
    for a in pack_raw["channel_adjustments"]:
        for ref in a.get("evidence_refs", []):
            assert "ads_bridge" not in ref


def test_feedback_plan_with_flag_promotes(tmp_path: Path) -> None:
    _seed_optimization_recommendation_pack(tmp_path / "mem")
    _seed_ads_bridge_pack(tmp_path / "mem")
    code, stdout = _run([
        "feedback-plan",
        "--client", "acme",
        "--include-ads-bridge",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    pack_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    promoted_tasks = [
        t for t in pack_raw["suggested_tasks"]
        if any("ads_bridge" in r for r in t.get("evidence_refs", []))
    ]
    assert len(promoted_tasks) >= 1
    # google_ads channel adjustment present.
    google_adj = [
        a for a in pack_raw["channel_adjustments"]
        if a.get("channel") == "google_ads"
    ]
    assert google_adj


def test_feedback_plan_with_flag_audit_records_promotion(tmp_path: Path) -> None:
    _seed_optimization_recommendation_pack(tmp_path / "mem")
    _seed_ads_bridge_pack(tmp_path / "mem")
    code, _ = _run([
        "feedback-plan",
        "--client", "acme",
        "--include-ads-bridge",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    audit_root = tmp_path / "mem" / "acme" / "audit"
    content = "\n".join(
        f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl")
    )
    assert "ads_bridge_promotion" in content
    assert "promoted" in content
    assert "campaign_feedback_pack" in content


# ============================================================
# apply-feedback --include-ads-bridge
# ============================================================


def _seed_feedback_pack(root: Path, *, client: str = "acme") -> None:
    """Minimal feedback pack to satisfy apply-feedback pre-requisite."""
    from core.feedback.models import (
        CAMPAIGN_FEEDBACK_PACK_KIND,
        CampaignFeedbackPack,
        ExecutiveSummary,
        FeedbackStats,
    )
    from core.feedback.models import (
        SINGLETON_ID as FB_SINGLETON,
    )

    mem = JsonFileMemory(root)
    pack = CampaignFeedbackPack(
        client_slug=client,
        recommendation_pack_id="rec-1",
        recommendation_pack_contract_version="optimization-recommendation-pack.v1",
        executive_summary=ExecutiveSummary(
            headline="t", paragraphs=["p"], suggested_meeting_agenda=["a"],
        ),
        suggested_tasks=[], channel_adjustments=[], content_suggestions=[],
        seo_recommendations=[], email_recommendations=[],
        social_recommendations=[],
        stats=FeedbackStats(
            total_suggested_tasks=0, high_priority_tasks=0,
            channel_adjustments=0, content_suggestions=0,
            seo_recommendations=0, email_recommendations=0,
            social_recommendations=0,
        ),
        created_at=_now(),
        rule_set_id="feedback-planner.v1",
    )
    mem.put(client, CAMPAIGN_FEEDBACK_PACK_KIND, FB_SINGLETON,
            pack.model_dump(mode="json"))


def test_apply_feedback_without_flag_does_not_promote(tmp_path: Path) -> None:
    _seed_feedback_pack(tmp_path / "mem")
    _seed_ads_bridge_pack(tmp_path / "mem")
    code, stdout = _run([
        "apply-feedback",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    plan_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    for a in plan_raw["actions"]:
        for ref in a.get("evidence_refs", []):
            assert "ads_bridge" not in ref


def test_apply_feedback_with_flag_promotes(tmp_path: Path) -> None:
    _seed_feedback_pack(tmp_path / "mem")
    _seed_ads_bridge_pack(tmp_path / "mem")
    code, stdout = _run([
        "apply-feedback",
        "--client", "acme",
        "--include-ads-bridge",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    plan_raw = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    promoted_actions = [
        a for a in plan_raw["actions"]
        if any("ads_bridge" in r for r in a.get("evidence_refs", []))
    ]
    assert len(promoted_actions) >= 1
    assert promoted_actions[0]["channel"] == "google_ads"
