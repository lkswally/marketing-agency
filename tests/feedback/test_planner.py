"""FeedbackPlanner tests — end-to-end with mocked metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.analytics import AnalyticsAnalyzer, AnalyticsImporter, MetricSource
from core.feedback import (
    CAMPAIGN_FEEDBACK_PACK_KIND,
    SINGLETON_ID,
    ChannelPriority,
    ContentSuggestionKind,
    FeedbackPlanner,
    SuggestedTaskCategory,
    SuggestedTaskPriority,
)
from core.memory import JsonFileMemory
from core.pipeline import PipelineOrchestrator

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _import_all(mem: JsonFileMemory, client: str) -> None:
    importer = AnalyticsImporter(memory=mem)
    pairs = [
        (FIXTURES / "ga4_demo.csv", MetricSource.GA4),
        (FIXTURES / "sc_demo.csv", MetricSource.SEARCH_CONSOLE),
        (FIXTURES / "social_demo.csv", MetricSource.SOCIAL),
        (FIXTURES / "email_demo.csv", MetricSource.EMAIL),
    ]
    for path, src in pairs:
        importer.import_file(client_slug=client, source=src, file_path=path)
    AnalyticsAnalyzer(memory=mem).persist(
        AnalyticsAnalyzer(memory=mem).analyze(client)
    )


def _full_stack(tmp_path: Path, *, client: str = "acme-bootstrapped") -> JsonFileMemory:
    """Run the full campaign pipeline + analytics so the feedback
    planner has every upstream artifact."""
    mem = JsonFileMemory(tmp_path / "mem")
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    orch.run_from_file(DEMO_INTAKE)
    _import_all(mem, client)
    return mem


# ---------- happy path ----------

def test_plan_succeeds_with_full_stack(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    assert pack.client_slug == "acme-bootstrapped"
    assert pack.recommendation_pack_id
    assert pack.snapshot_id
    assert pack.run_summary_id
    assert pack.suggested_tasks
    assert pack.channel_adjustments


def test_plan_high_priority_count_in_stats(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    high = [
        t for t in pack.suggested_tasks
        if t.priority is SuggestedTaskPriority.HIGH
    ]
    assert pack.stats.high_priority_tasks == len(high)


def test_plan_pause_recommended_for_worst_channel(tmp_path: Path) -> None:
    """x has 3000 imp + 1 click in the fixture; planner should
    recommend pausing it."""
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    pauses = [
        a for a in pack.channel_adjustments
        if a.new_priority is ChannelPriority.PAUSE
    ]
    assert any(a.channel == "x" for a in pauses)


def test_plan_promotes_best_channel(tmp_path: Path) -> None:
    """linkedin is the best channel in the fixture; planner should
    recommend HIGH priority for it."""
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    promotions = [
        a for a in pack.channel_adjustments
        if a.new_priority is ChannelPriority.HIGH
    ]
    assert any(a.channel == "linkedin" for a in promotions)


def test_plan_includes_seo_recommendations(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    assert pack.seo_recommendations
    # All have positive score and a rationale.
    for s in pack.seo_recommendations:
        assert s.opportunity_score > 0
        assert s.rationale


def test_plan_includes_email_recommendations(tmp_path: Path) -> None:
    """Email fixture has campaign-002 with click rate 0.02/1100 ≈
    1.8% → below threshold; expect a click-rate recommendation."""
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    # At least one campaign emitted a recommendation.
    assert pack.email_recommendations


def test_plan_top_content_suggestion_is_repeat(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    if pack.content_suggestions:
        repeats = [
            c for c in pack.content_suggestions
            if c.kind is ContentSuggestionKind.REPEAT
        ]
        assert repeats


def test_plan_executive_summary_present(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    assert pack.executive_summary
    assert pack.executive_summary.headline
    assert pack.executive_summary.paragraphs
    assert pack.executive_summary.suggested_meeting_agenda


def test_plan_includes_measurement_task(tmp_path: Path) -> None:
    """The planner adds a 'import next cycle metrics' task."""
    mem = _full_stack(tmp_path)
    pack = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    measurement = [
        t for t in pack.suggested_tasks
        if t.category is SuggestedTaskCategory.MEASUREMENT
    ]
    assert measurement


# ---------- failure path ----------

def test_plan_without_recommendation_pack_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError) as ei:
        FeedbackPlanner(memory=mem).plan("ghost")
    assert "OptimizationRecommendationPack" in str(ei.value)
    assert "mkt analyze-metrics" in str(ei.value)


def test_plan_with_only_analytics_works(tmp_path: Path) -> None:
    """Even without the campaign pipeline (no run summary, no
    creative, no visual), the planner produces a pack."""
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = FeedbackPlanner(memory=mem).plan("acme")
    assert pack.client_slug == "acme"
    assert pack.recommendation_pack_id
    assert pack.run_summary_id is None
    assert pack.task_pack_id is None
    assert pack.creative_pack_id is None
    assert pack.suggested_tasks  # at least from rec_pack


# ---------- determinism ----------

def test_two_plans_produce_same_counts(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    a = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    b = FeedbackPlanner(memory=mem).plan("acme-bootstrapped")
    assert a.stats.total_suggested_tasks == b.stats.total_suggested_tasks
    assert a.stats.channel_adjustments == b.stats.channel_adjustments
    assert a.stats.seo_recommendations == b.stats.seo_recommendations


# ---------- persistence + audit ----------

def test_persist_writes_to_memory(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    planner = FeedbackPlanner(memory=mem)
    pack = planner.plan("acme-bootstrapped")
    planner.persist(pack)
    assert mem.exists("acme-bootstrapped", CAMPAIGN_FEEDBACK_PACK_KIND, SINGLETON_ID)
    loaded = planner.load_latest("acme-bootstrapped")
    assert loaded.pack_id == pack.pack_id


def test_persist_emits_audit_event(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    planner = FeedbackPlanner(memory=mem)
    planner.persist(planner.plan("acme-bootstrapped"))
    events = mem.read_audit_events("acme-bootstrapped")
    actions = [
        e.payload.get("campaign_feedback_pack", {}).get("action")
        for e in events
        if "campaign_feedback_pack" in e.payload
    ]
    assert "planned" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []


# ---------- safety ----------

def test_planner_does_not_import_http_or_env() -> None:
    import inspect

    import core.feedback.planner as mod
    src = inspect.getsource(mod)
    for forbidden in (
        "import requests", "import httpx", "urllib.request",
        "os.environ", "import anthropic",
    ):
        assert forbidden not in src


def test_pack_has_no_credential_fields() -> None:
    from core.feedback import CampaignFeedbackPack
    fields = set(CampaignFeedbackPack.model_fields.keys())
    for forbidden in ("token", "api_key", "secret", "credential", "url"):
        assert forbidden not in fields
