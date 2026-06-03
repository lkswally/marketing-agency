"""IterationPlanner tests — end-to-end with feedback pack present."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.analytics import AnalyticsAnalyzer, AnalyticsImporter, MetricSource
from core.feedback import FeedbackPlanner
from core.iteration import (
    NEXT_CAMPAIGN_ITERATION_PLAN_KIND,
    SINGLETON_ID,
    IterationActionKind,
    IterationActionPriority,
    IterationPlanner,
    NewContentKind,
)
from core.memory import JsonFileMemory
from core.pipeline import PipelineOrchestrator

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _full_stack(tmp_path: Path) -> JsonFileMemory:
    mem = JsonFileMemory(tmp_path / "mem")
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    # Import all analytics fixtures.
    importer = AnalyticsImporter(memory=mem)
    for fixture, source in [
        ("ga4_demo.csv", MetricSource.GA4),
        ("sc_demo.csv", MetricSource.SEARCH_CONSOLE),
        ("social_demo.csv", MetricSource.SOCIAL),
        ("email_demo.csv", MetricSource.EMAIL),
    ]:
        importer.import_file(
            client_slug=summary.client_slug, source=source,
            file_path=FIXTURES / fixture,
        )
    analyzer = AnalyticsAnalyzer(memory=mem)
    analyzer.persist(analyzer.analyze(summary.client_slug))
    fp = FeedbackPlanner(memory=mem)
    fp.persist(fp.plan(summary.client_slug))
    return mem


# ---------- happy path ----------

def test_plan_succeeds_with_full_stack(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    assert plan.client_slug == "acme-bootstrapped"
    assert plan.feedback_pack_id
    assert plan.run_summary_id
    assert plan.actions  # at least from the feedback pack
    assert plan.calendar
    assert plan.suggested_tasks


def test_plan_emits_repeat_for_top_content(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    repeats = plan.actions_of_kind(IterationActionKind.REPEAT_PIECE)
    assert repeats
    for a in repeats:
        assert a.priority is IterationActionPriority.HIGH


def test_plan_emits_channel_promote_for_best_channel(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    promotes = plan.actions_of_kind(IterationActionKind.CHANNEL_PROMOTE)
    assert promotes
    assert any(a.channel == "linkedin" for a in promotes)


def test_plan_emits_channel_pause_for_worst_channel(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    pauses = plan.actions_of_kind(IterationActionKind.CHANNEL_PAUSE)
    assert pauses
    assert any(a.channel == "x" for a in pauses)


def test_new_content_includes_seo_articles(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    seo = [
        i for i in plan.new_content_ideas
        if i.kind is NewContentKind.SEO_ARTICLE
    ]
    assert seo


def test_new_content_includes_social_for_best_channel(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    social = [
        i for i in plan.new_content_ideas
        if i.kind is NewContentKind.SOCIAL_POST
    ]
    assert social


def test_ab_test_hypotheses_have_success_criteria(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    if plan.ab_test_hypotheses:
        for h in plan.ab_test_hypotheses:
            assert h.success_metric
            assert h.success_threshold


def test_calendar_skips_paused_channels(tmp_path: Path) -> None:
    """The fixture pushes x to PAUSE. The calendar should not
    include any week scheduled for x."""
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    for entry in plan.calendar:
        assert entry.channel != "x"


def test_suggested_tasks_include_measurement_task(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    measurement = [
        t for t in plan.suggested_tasks if t.category == "measurement"
    ]
    assert measurement


def test_executive_summary_present(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    plan = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    assert plan.executive_summary
    assert plan.executive_summary.headline
    assert plan.executive_summary.paragraphs
    assert plan.executive_summary.suggested_meeting_agenda


# ---------- failure path ----------

def test_plan_without_feedback_pack_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError) as ei:
        IterationPlanner(memory=mem).plan("ghost")
    assert "CampaignFeedbackPack" in str(ei.value)
    assert "mkt feedback-plan" in str(ei.value)


# ---------- no automatic mutation ----------

def test_planner_does_not_modify_upstream_packs(tmp_path: Path) -> None:
    """Reading the iteration planner should not change any upstream
    pack id or content. Sanity: fetch the feedback pack id before and
    after."""
    mem = _full_stack(tmp_path)
    feedback_raw_before = mem.get("acme-bootstrapped", "campaign_feedback_pack", "current")
    IterationPlanner(memory=mem).plan("acme-bootstrapped")
    feedback_raw_after = mem.get("acme-bootstrapped", "campaign_feedback_pack", "current")
    assert feedback_raw_before == feedback_raw_after


# ---------- determinism ----------

def test_two_plans_produce_same_counts(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    a = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    b = IterationPlanner(memory=mem).plan("acme-bootstrapped")
    assert a.stats.total_actions == b.stats.total_actions
    assert a.stats.new_content_ideas == b.stats.new_content_ideas
    assert a.stats.calendar_entries == b.stats.calendar_entries


# ---------- persistence + audit ----------

def test_persist_writes_to_memory(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    planner = IterationPlanner(memory=mem)
    plan = planner.plan("acme-bootstrapped")
    planner.persist(plan)
    assert mem.exists("acme-bootstrapped", NEXT_CAMPAIGN_ITERATION_PLAN_KIND, SINGLETON_ID)
    loaded = planner.load_latest("acme-bootstrapped")
    assert loaded.plan_id == plan.plan_id


def test_persist_emits_audit_event(tmp_path: Path) -> None:
    mem = _full_stack(tmp_path)
    planner = IterationPlanner(memory=mem)
    planner.persist(planner.plan("acme-bootstrapped"))
    events = mem.read_audit_events("acme-bootstrapped")
    actions = [
        e.payload.get("next_campaign_iteration_plan", {}).get("action")
        for e in events
        if "next_campaign_iteration_plan" in e.payload
    ]
    assert "planned" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []


# ---------- safety ----------

def test_planner_does_not_import_http_or_env() -> None:
    import inspect

    import core.iteration.planner as mod
    src = inspect.getsource(mod)
    for forbidden in (
        "import requests", "import httpx", "urllib.request",
        "os.environ", "import anthropic",
    ):
        assert forbidden not in src
