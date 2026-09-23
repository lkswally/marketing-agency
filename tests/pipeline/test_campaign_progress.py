"""CampaignRunProgress checkpoint (job-execution-robustness).

Covers: the transition semantics from the approved design (succeeded /
failed / blocked / skipped / interrupted), that a real job-driven run
persists a correct, complete checkpoint, that the legacy
`mkt run-campaign` path is untouched (no checkpoint at all), and that a
partial/interrupted run is queryable — without inventing a new persisted
job state, and explicitly NOT transactional (no rollback anywhere).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.application.context import OperationContext
from core.jobs import InlineJobRunner, JobRegistry, JobState
from core.jobs.operations.campaign import register_campaign_operations
from core.memory import JsonFileMemory
from core.pipeline.models import StageId, StageOutcome
from core.pipeline.orchestrator import PipelineOrchestrator
from core.pipeline.progress import (
    CAMPAIGN_RUN_PROGRESS_KIND,
    CampaignProgressTracker,
    CampaignRunProgress,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _risky_intake(tmp_path: Path) -> Path:
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    path = tmp_path / "risky.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _read_progress(mem: JsonFileMemory, client_slug: str, job_id: str) -> CampaignRunProgress:
    raw = mem.get(client_slug, CAMPAIGN_RUN_PROGRESS_KIND, job_id)
    return CampaignRunProgress.model_validate(raw)


# ---------- transition semantics, tested directly against the tracker ----------


def test_tracker_succeeded_stage_appends_to_completed_and_clears_current(
    tmp_path: Path,
) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    tracker = CampaignProgressTracker(
        mem, job_id="job-1", client_slug="acme", correlation_id="corr-1",
    )
    tracker.stage_starting(StageId.STRATEGY)
    doc = _read_progress(mem, "acme", "job-1")
    assert doc.current_stage is StageId.STRATEGY
    assert doc.last_stage_outcome is None

    tracker.stage_finished(StageId.STRATEGY, StageOutcome.SUCCEEDED)
    doc = _read_progress(mem, "acme", "job-1")
    assert doc.stages_completed == [StageId.STRATEGY]
    assert doc.current_stage is None
    assert doc.last_stage_outcome == "succeeded"


def test_tracker_failed_stage_does_not_count_as_completed(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    tracker = CampaignProgressTracker(
        mem, job_id="job-2", client_slug="acme", correlation_id=None,
    )
    tracker.stage_starting(StageId.STRATEGY)
    tracker.stage_finished(StageId.STRATEGY, StageOutcome.FAILED)
    doc = _read_progress(mem, "acme", "job-2")
    assert doc.stages_completed == []
    assert doc.current_stage is None
    assert doc.last_stage_outcome == "failed"


def test_tracker_blocked_stage_not_completed_not_treated_as_interrupted(
    tmp_path: Path,
) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    tracker = CampaignProgressTracker(
        mem, job_id="job-3", client_slug="acme", correlation_id=None,
    )
    tracker.stage_starting(StageId.APPROVAL)
    tracker.stage_finished(StageId.APPROVAL, StageOutcome.BLOCKED)
    doc = _read_progress(mem, "acme", "job-3")
    assert doc.stages_completed == []
    # Cleared, exactly like succeeded/failed — a policy decision is not
    # an interruption.
    assert doc.current_stage is None
    assert doc.last_stage_outcome == "blocked"


def test_tracker_skipped_stages_recorded_separately(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    tracker = CampaignProgressTracker(
        mem, job_id="job-4", client_slug="acme", correlation_id=None,
    )
    tracker.stages_skipped([StageId.CREATIVE, StageId.VISUAL])
    doc = _read_progress(mem, "acme", "job-4")
    assert doc.stages_skipped == [StageId.CREATIVE, StageId.VISUAL]
    assert doc.stages_completed == []


def test_tracker_interrupted_mid_stage_leaves_diagnosable_state(tmp_path: Path) -> None:
    """The exact scenario the design calls INTERRUPTED_DURING_STAGE_N:
    stage_starting() ran, stage_finished() never did (simulating a crash
    between the two — no new persisted job state is invented for this;
    the interpretation comes from reading current_stage + last_stage_outcome
    together)."""
    mem = JsonFileMemory(tmp_path / "mem")
    tracker = CampaignProgressTracker(
        mem, job_id="job-5", client_slug="acme", correlation_id="corr-5",
    )
    tracker.stage_starting(StageId.STRATEGY)
    tracker.stage_finished(StageId.STRATEGY, StageOutcome.SUCCEEDED)
    tracker.stage_starting(StageId.CREATIVE)
    # No stage_finished() call — this IS the simulated crash.

    doc = _read_progress(mem, "acme", "job-5")
    assert doc.stages_completed == [StageId.STRATEGY]
    assert doc.current_stage is StageId.CREATIVE
    assert doc.last_stage_outcome is None
    assert StageId.CREATIVE not in doc.stages_completed
    assert StageId.CREATIVE not in doc.stages_skipped
    # This combination — current_stage set, absent from both lists,
    # last_stage_outcome None — is precisely "interrupted during
    # StageId.CREATIVE", diagnosable without a new persisted state.


def test_progress_is_never_transactional(tmp_path: Path) -> None:
    """Explicit, direct proof against the "transactional" framing: once
    a stage is marked completed, nothing rolls it back even if a LATER
    stage fails — the checkpoint only ever grows forward."""
    mem = JsonFileMemory(tmp_path / "mem")
    tracker = CampaignProgressTracker(
        mem, job_id="job-6", client_slug="acme", correlation_id=None,
    )
    tracker.stage_starting(StageId.STRATEGY)
    tracker.stage_finished(StageId.STRATEGY, StageOutcome.SUCCEEDED)
    tracker.stage_starting(StageId.APPROVAL)
    tracker.stage_finished(StageId.APPROVAL, StageOutcome.FAILED)

    doc = _read_progress(mem, "acme", "job-6")
    # STRATEGY's completion is untouched by APPROVAL's later failure —
    # no rollback, no compensation, exactly as documented.
    assert StageId.STRATEGY in doc.stages_completed


# ---------- real, job-driven pipeline runs ----------


def test_successful_job_driven_run_has_full_progress_checkpoint(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    reg = JobRegistry()
    register_campaign_operations(reg)
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=reg)
    ctx = OperationContext(client_slug="acme-bootstrapped", root=root, outputs_root=tmp_path / "out")
    record = runner.submit(
        ctx, operation="campaign.run", params={"intake_path": str(DEMO_INTAKE)},
    )
    result = runner.run(record.client_slug, record.job_id)
    assert result.state is JobState.COMPLETED

    doc = _read_progress(mem, "acme-bootstrapped", record.job_id)
    assert doc.job_id == record.job_id
    assert doc.stages_completed == [
        StageId.INTAKE, StageId.STRATEGY, StageId.APPROVAL,
        StageId.CREATIVE, StageId.VISUAL, StageId.SUMMARY,
    ]
    assert doc.stages_skipped == []
    assert doc.current_stage is None
    assert doc.last_stage_outcome == "succeeded"


def test_legacy_run_campaign_path_writes_no_progress_checkpoint(tmp_path: Path) -> None:
    """The synchronous `mkt run-campaign` CLI path (job_id=None) must
    remain byte-for-byte unaffected — no progress entity at all."""
    mem = JsonFileMemory(tmp_path / "mem")
    orchestrator = PipelineOrchestrator(mem, outputs_root=tmp_path / "out")
    summary = orchestrator.run_from_file(DEMO_INTAKE)
    assert summary.client_slug == "acme-bootstrapped"

    assert mem.list("acme-bootstrapped", CAMPAIGN_RUN_PROGRESS_KIND) == []


def test_blocked_job_driven_run_skips_creative_and_visual_in_checkpoint(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mem"
    reg = JobRegistry()
    register_campaign_operations(reg)
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=reg)
    risky = _risky_intake(tmp_path)
    ctx = OperationContext(client_slug="acme-bootstrapped", root=root, outputs_root=tmp_path / "out")
    record = runner.submit(
        ctx, operation="campaign.run",
        params={"intake_path": str(risky), "require_approval": True},
    )
    result = runner.run(record.client_slug, record.job_id)
    assert result.state is JobState.WAITING_APPROVAL

    doc = _read_progress(mem, "acme-bootstrapped", record.job_id)
    assert StageId.APPROVAL not in doc.stages_completed  # BLOCKED, not SUCCEEDED
    assert doc.last_stage_outcome == "blocked"
    assert doc.stages_skipped == [StageId.CREATIVE, StageId.VISUAL]
    assert doc.current_stage is None
