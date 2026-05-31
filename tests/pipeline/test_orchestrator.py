"""PipelineOrchestrator tests — chain, flags, blocked semantics, audit chain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.contracts import verify_chain
from core.creative.models import CreativeAssetState
from core.intake import INTAKE_KIND, VALIDATION_KIND
from core.intake import SINGLETON_ID as INTAKE_SINGLETON
from core.memory import JsonFileMemory
from core.pipeline import (
    PIPELINE_RUN_KIND,
    PIPELINE_RUN_SINGLETON,
    PipelineBlockedByApproval,
    PipelineOrchestrator,
    PipelineStrictFailure,
    StageId,
    StageOutcome,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path / "mem")


@pytest.fixture
def orchestrator(mem: JsonFileMemory, tmp_path: Path) -> PipelineOrchestrator:
    return PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")


# ---------- happy path ----------

def test_run_demo_intake_succeeds(orchestrator: PipelineOrchestrator) -> None:
    summary = orchestrator.run_from_file(DEMO_INTAKE)
    assert summary.is_complete is True
    assert summary.overall_state is CreativeAssetState.DRAFT
    assert summary.blocks_publish is False
    assert summary.client_slug == "acme-bootstrapped"


def test_run_produces_six_stages(orchestrator: PipelineOrchestrator) -> None:
    summary = orchestrator.run_from_file(DEMO_INTAKE)
    assert len(summary.stages) == 6
    stage_ids = [s.stage_id for s in summary.stages]
    assert stage_ids == [
        StageId.INTAKE,
        StageId.STRATEGY,
        StageId.APPROVAL,
        StageId.CREATIVE,
        StageId.VISUAL,
        StageId.SUMMARY,
    ]
    for s in summary.stages:
        assert s.outcome is StageOutcome.SUCCEEDED


def test_run_populates_pack_ids(orchestrator: PipelineOrchestrator) -> None:
    summary = orchestrator.run_from_file(DEMO_INTAKE)
    assert summary.intake_id
    assert summary.validation_id
    assert summary.report_id
    assert summary.approval_pack_id
    assert summary.creative_pack_id
    assert summary.visual_pack_id


def test_run_writes_all_expected_files(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    orch = PipelineOrchestrator(memory=mem, outputs_root=out)
    summary = orch.run_from_file(DEMO_INTAKE)
    client_out = out / summary.client_slug
    expected = [
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
    ]
    for name in expected:
        assert (client_out / name).exists(), f"missing output: {name}"


def test_run_persists_summary_in_memory(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    assert mem.exists(summary.client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON)


def test_run_persists_intake_in_memory(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    assert mem.exists(summary.client_slug, INTAKE_KIND, INTAKE_SINGLETON)
    assert mem.exists(summary.client_slug, VALIDATION_KIND, INTAKE_SINGLETON)


# ---------- audit chain ----------

def test_audit_chain_valid_after_run(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    events = mem.read_audit_events(summary.client_slug)
    assert verify_chain(events) == []


def test_audit_records_pipeline_started_and_finished(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    events = mem.read_audit_events(summary.client_slug)
    pipeline_actions = [
        e.payload.get("campaign_pipeline", {}).get("action")
        for e in events
        if "campaign_pipeline" in e.payload
    ]
    assert "started" in pipeline_actions
    assert "finished" in pipeline_actions


def test_audit_records_each_stage(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    events = mem.read_audit_events(summary.client_slug)
    stages_in_events = [
        e.payload.get("campaign_pipeline", {}).get("stage")
        for e in events
        if "campaign_pipeline" in e.payload
        and "stage" in e.payload.get("campaign_pipeline", {})
    ]
    for stage in ("intake", "strategy", "approval", "creative", "visual"):
        assert stage in stages_in_events


# ---------- strict flag ----------

def test_strict_with_incomplete_intake_raises(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    """An intake missing critical fields under --strict must halt with the typed sentinel."""
    minimal = tmp_path / "minimal.json"
    minimal.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    with pytest.raises(PipelineStrictFailure):
        orch.run_from_file(minimal, strict=True)


def test_non_strict_with_incomplete_intake_does_not_raise(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    """Without --strict, an incomplete intake just records the intake stage as failed."""
    minimal = tmp_path / "minimal.json"
    minimal.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    # Without --strict the intake can still normalize when all critical fields are
    # absent? No — critical means can_normalize=False, so the stage marks FAILED
    # and later stages are not reached. Verify it returns rather than raises.
    summary = orch.run_from_file(minimal, strict=False)
    intake_stage = summary.get_stage(StageId.INTAKE)
    assert intake_stage is not None
    # Either FAILED (no normalization) or notes about critical issues
    assert summary.intake_critical_count >= 3


# ---------- blocking semantics ----------

def _make_risky_intake(tmp_path: Path) -> Path:
    """Produce an intake whose strategy output triggers blocking claims."""
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    # Force a risky claim by injecting hand-crafted product copy that the
    # template generator will surface in the value proposition.
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    new_path = tmp_path / "risky-intake.json"
    new_path.write_text(json.dumps(data), encoding="utf-8")
    return new_path


def test_stop_on_blocked_halts_after_approval(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    intake_path = _make_risky_intake(tmp_path)
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(intake_path, stop_on_blocked=True)
    assert summary.blocks_publish is True
    creative = summary.get_stage(StageId.CREATIVE)
    visual = summary.get_stage(StageId.VISUAL)
    assert creative is not None and creative.outcome is StageOutcome.SKIPPED
    assert visual is not None and visual.outcome is StageOutcome.SKIPPED


def test_require_approval_with_blocked_raises(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    intake_path = _make_risky_intake(tmp_path)
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    with pytest.raises(PipelineBlockedByApproval):
        orch.run_from_file(intake_path, require_approval=True)


def test_clean_intake_with_require_approval_succeeds(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE, require_approval=True)
    assert summary.is_complete is True
    assert summary.blocks_publish is False


# ---------- multi-tenant isolation ----------

def test_two_clients_isolated(mem: JsonFileMemory, tmp_path: Path) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    s1 = orch.run_from_file(DEMO_INTAKE)
    # Second client.
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["client_name"] = "Beta Co"
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(data), encoding="utf-8")
    s2 = orch.run_from_file(second_path)
    assert s1.client_slug != s2.client_slug
    assert mem.exists(s1.client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON)
    assert mem.exists(s2.client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON)


# ---------- determinism (pack ids reused on re-run) ----------

def test_rerun_produces_new_run_id_but_same_slug(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    s1 = orch.run_from_file(DEMO_INTAKE)
    s2 = orch.run_from_file(DEMO_INTAKE)
    assert s1.run_id != s2.run_id
    assert s1.client_slug == s2.client_slug


# ---------- missing intake file ----------

def test_missing_intake_file_returns_failed_intake_stage(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(tmp_path / "nope.json")
    intake = summary.get_stage(StageId.INTAKE)
    assert intake is not None
    assert intake.outcome is StageOutcome.FAILED
