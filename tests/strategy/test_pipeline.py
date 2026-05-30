"""End-to-end pipeline tests for the campaign strategy engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.contracts import WorkflowRunStatus
from core.memory import JsonFileMemory
from core.strategy import (
    CAMPAIGN_STRATEGY_VERSION,
    REPORT_KIND,
    SINGLETON_ID,
    CampaignStrategyReport,
    StrategyPipeline,
    StrategyPipelineError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


# ---------- happy path with the demo client ----------

def test_pipeline_runs_demo_brief_successfully(mem: JsonFileMemory) -> None:
    pipeline = StrategyPipeline(memory=mem)
    result = pipeline.run_from_path(DEMO_BRIEF)
    assert result.summary.status is WorkflowRunStatus.SUCCEEDED
    assert isinstance(result.report, CampaignStrategyReport)
    assert result.report.client_slug == "demo-saas"
    assert result.report.contract_version == CAMPAIGN_STRATEGY_VERSION


def test_pipeline_persists_report(mem: JsonFileMemory) -> None:
    pipeline = StrategyPipeline(memory=mem)
    result = pipeline.run_from_path(DEMO_BRIEF)
    raw = mem.get("demo-saas", REPORT_KIND, SINGLETON_ID)
    persisted = CampaignStrategyReport.model_validate(raw)
    assert persisted.report_id == result.report.report_id


def test_pipeline_persists_each_strategy_artifact(mem: JsonFileMemory) -> None:
    pipeline = StrategyPipeline(memory=mem)
    pipeline.run_from_path(DEMO_BRIEF)
    # 11 phases × at least one artifact kind each.
    for kind in [
        "strategy_input_brief",
        "strategy_diagnosis",
        "strategy_target_audience",
        "strategy_buyer_persona",
        "strategy_competitor_benchmark",
        "strategy_value_proposition",
        "strategy_channel_recommendation",
        "strategy_keyword_plan",
        "strategy_campaign_strategy",
        "strategy_creative_brief_pack",
        "strategy_email_sequence",
        "strategy_reels_pack",
        "strategy_schedule",
        "strategy_approval_checklist",
        "strategy_risk_assessment",
        "campaign_strategy_report",
    ]:
        assert mem.exists("demo-saas", kind, SINGLETON_ID), f"missing kind: {kind}"


def test_pipeline_audit_trail_chain_valid(mem: JsonFileMemory) -> None:
    from core.contracts import verify_chain

    pipeline = StrategyPipeline(memory=mem)
    pipeline.run_from_path(DEMO_BRIEF)
    events = mem.read_audit_events("demo-saas")
    assert verify_chain(events) == []
    event_types = [e.event_type.value for e in events]
    assert event_types[0] == "workflow_started"
    assert event_types[-1] == "workflow_finished"


def test_pipeline_writes_markdown_when_requested(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    pipeline = StrategyPipeline(memory=mem)
    output = tmp_path / "out" / "report.md"
    result = pipeline.run_from_path(DEMO_BRIEF, write_markdown_to=output)
    assert result.report_markdown_path == output
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Campaign Strategy Report")


# ---------- report shape ----------

def test_report_has_all_20_sections_populated(mem: JsonFileMemory) -> None:
    pipeline = StrategyPipeline(memory=mem)
    result = pipeline.run_from_path(DEMO_BRIEF)
    r = result.report
    # Required sub-objects exist (Pydantic ensures non-None).
    assert r.executive_summary.headline
    assert r.diagnosis.stage_observed
    assert r.target_audience.label
    assert r.buyer_persona is not None
    assert r.value_proposition.headline
    assert r.competitor_benchmark.competitors
    assert r.channel_recommendation.channels
    assert r.keyword_plan.clusters
    assert r.campaign_strategy.objective
    assert r.suggested_pieces
    assert r.creative_brief_pack.briefs
    assert r.social_post_drafts
    assert r.email_sequence.emails
    assert r.reels_script_pack.scripts
    assert r.schedule.entries
    assert r.approval_checklist.items
    assert r.risk_assessment.risks
    assert r.next_steps


def test_report_carries_brief_id(mem: JsonFileMemory) -> None:
    pipeline = StrategyPipeline(memory=mem)
    result = pipeline.run_from_path(DEMO_BRIEF)
    assert result.report.brief_id == "demo-saas:current"


# ---------- robustness ----------

def test_pipeline_rejects_missing_brief_file(tmp_path: Path, mem: JsonFileMemory) -> None:
    pipeline = StrategyPipeline(memory=mem)
    with pytest.raises(FileNotFoundError):
        pipeline.run_from_path(tmp_path / "nope.json")


def test_pipeline_two_clients_isolated(mem: JsonFileMemory, tmp_path: Path) -> None:
    # Make a second brief with a different slug + name.
    import json

    second = json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    second["client"]["slug"] = "demo-co"
    second["client"]["name"] = "Demo Co"
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(second), encoding="utf-8")

    pipeline = StrategyPipeline(memory=mem)
    r1 = pipeline.run_from_path(DEMO_BRIEF)
    r2 = pipeline.run_from_path(second_path)
    assert r1.report.client_slug == "demo-saas"
    assert r2.report.client_slug == "demo-co"
    assert mem.exists("demo-saas", REPORT_KIND, SINGLETON_ID)
    assert mem.exists("demo-co", REPORT_KIND, SINGLETON_ID)
    # No cross-tenant leak.
    assert not mem.exists("demo-saas", REPORT_KIND, "wrong")


# ---------- StrategyPipelineError sanity ----------

def test_pipeline_error_exists() -> None:
    assert issubclass(StrategyPipelineError, RuntimeError)
