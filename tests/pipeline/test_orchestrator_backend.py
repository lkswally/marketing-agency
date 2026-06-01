"""Orchestrator-level: --backend propagation, summary fields, audit events."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.contracts import verify_chain
from core.memory import JsonFileMemory
from core.pipeline import (
    PIPELINE_RUN_KIND,
    PIPELINE_RUN_SINGLETON,
    PipelineOrchestrator,
)
from core.strategy import (
    ClaudeStrategyBackend,
    RefusingClaudeInvoker,
    TemplatedStrategyBackend,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path / "mem")


@pytest.fixture
def orch(mem: JsonFileMemory, tmp_path: Path) -> PipelineOrchestrator:
    return PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")


# ---------- default (templated) ----------


def test_no_backend_argument_keeps_templated_defaults(orch) -> None:
    summary = orch.run_from_file(DEMO_INTAKE)
    assert summary.backend_requested == "templated"
    assert summary.backend_effective == "templated"
    assert summary.backend_fallback_count == 0
    assert summary.backend_fallback_notes == []


def test_explicit_templated_backend_is_identical_to_default(mem, tmp_path) -> None:
    o1 = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out1")
    s1 = o1.run_from_file(DEMO_INTAKE)
    o2 = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out2")
    s2 = o2.run_from_file(DEMO_INTAKE, strategy_backend=TemplatedStrategyBackend())
    assert s1.backend_requested == s2.backend_requested == "templated"
    assert s1.backend_effective == s2.backend_effective == "templated"
    # Counts of each pipeline stage outcome should match too.
    assert s1.count_by_outcome() == s2.count_by_outcome()


# ---------- claude backend with refusing invoker ----------


def test_claude_with_refusing_invoker_falls_back_six_times(orch) -> None:
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    assert summary.backend_requested == "claude"
    assert summary.backend_effective == "templated"  # all 6 fell back
    assert summary.backend_fallback_count == 6


def test_fallback_events_recorded_in_audit_trail(mem, tmp_path) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)

    events = mem.read_audit_events(summary.client_slug)
    actions = [
        e.payload.get("campaign_pipeline", {}).get("action")
        for e in events
        if "campaign_pipeline" in e.payload
    ]
    # Six fallback events between strategy and finished.
    assert actions.count("strategy_backend_fallback") == 6
    # Audit chain still valid after the extra events.
    assert verify_chain(events) == []


def test_started_event_records_requested_backend(mem, tmp_path) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    events = mem.read_audit_events(summary.client_slug)
    started = [
        e for e in events
        if e.payload.get("campaign_pipeline", {}).get("action") == "started"
    ]
    assert started
    assert started[0].payload["campaign_pipeline"]["backend_requested"] == "claude"


def test_finished_event_records_effective_backend(mem, tmp_path) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    events = mem.read_audit_events(summary.client_slug)
    finished = [
        e for e in events
        if e.payload.get("campaign_pipeline", {}).get("action") == "finished"
    ]
    assert finished
    payload = finished[0].payload["campaign_pipeline"]
    assert payload["backend_requested"] == "claude"
    assert payload["backend_effective"] == "templated"
    assert payload["backend_fallback_count"] == 6


def test_pipeline_still_completes_with_all_deliverables(mem, tmp_path) -> None:
    """The 12 standard outputs must exist even when Claude fully falls back."""
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    client_out = (tmp_path / "out") / summary.client_slug
    for name in (
        "intake.json",
        "intake-summary.md",
        "brief.json",
        "campaign-strategy.md",
        "approval-pack.md",
        "approval-pack.json",
        "creative-pack.md",
        "creative-pack.json",
        "visual-direction-pack.md",
        "visual-direction-pack.json",
        "campaign-final-summary.md",
        "campaign-final-summary.json",
    ):
        assert (client_out / name).exists(), name


def test_summary_persisted_in_memory_with_backend_fields(mem, tmp_path) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    raw = mem.get(summary.client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON)
    assert raw["backend_requested"] == "claude"
    assert raw["backend_effective"] == "templated"
    assert raw["backend_fallback_count"] == 6
    assert len(raw["backend_fallback_notes"]) == 6


# ---------- partial fallback → "mixed" ----------


def test_partial_fallback_yields_mixed_effective(mem, tmp_path) -> None:
    """If only some methods fall back, backend_effective == 'mixed'."""
    import json

    from core.strategy import ScriptedClaudeInvoker

    # Provide canned responses for exactly TWO methods; the other four will
    # raise (no canned response) and fall back.
    vp = json.dumps(
        {
            "headline": "Lorem ipsum dolor sit amet consectetur.",
            "category": "SaaS",
            "target_audience_label": "founders",
            "differentiators": ["x"],
            "proof_points": ["y"],
            "primary_benefit": None,
            "notes": None,
        }
    )
    cs = json.dumps(
        {
            "objective": "Activate trials",
            "duration_weeks": 6,
            "primary_kpi": "activation_rate",
            "secondary_kpis": [],
            "funnel_focus": "activation" if False else "conversion",
            "budget_estimate": None,
            "budget_currency": None,
            "big_idea": None,
            "narrative_arc": [],
        }
    )
    inv = ScriptedClaudeInvoker(
        responses={"value_proposition": vp, "campaign_strategy": cs}
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    assert summary.backend_requested == "claude"
    assert summary.backend_effective == "mixed"
    # 2 of 6 succeeded → 4 fell back.
    assert summary.backend_fallback_count == 4
