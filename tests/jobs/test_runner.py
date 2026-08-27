"""Tests for InlineJobRunner — lifecycle, idempotency, cancellation limits,
audit trail, no-argparse-dependency (MKT-11C)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.application.context import OperationContext
from core.application.result import ErrorCode
from core.jobs.models import JobOutcome, JobOutcomeStatus, JobState
from core.jobs.operations.demo import register_demo_operations
from core.jobs.registry import JobRegistry, JobRiskClass, OperationSpec
from core.jobs.repository import JobPersistenceError, JobRepository
from core.jobs.runner import InlineJobRunner, JobTransitionError
from core.memory import EntityNotFound, JsonFileMemory


def _runner(tmp_path: Path, *, registry: JobRegistry | None = None) -> InlineJobRunner:
    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    reg = registry
    if reg is None:
        reg = JobRegistry()
        register_demo_operations(reg)
    return InlineJobRunner(mem, root=root, registry=reg)


def _ctx(tmp_path: Path, client: str = "acme") -> OperationContext:
    return OperationContext(client_slug=client, root=tmp_path / "mem")


# ---------- submit ----------

def test_submit_creates_queued_job(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    record = runner.submit(_ctx(tmp_path), operation="demo.echo", params={"message": "hi"})
    assert record.state is JobState.QUEUED
    assert record.client_slug == "acme"
    assert record.operation == "demo.echo"


def test_submit_unknown_operation_raises(tmp_path: Path) -> None:
    from core.jobs.registry import UnknownOperationError

    runner = _runner(tmp_path)
    with pytest.raises(UnknownOperationError):
        runner.submit(_ctx(tmp_path), operation="nope", params={})


def test_submit_invalid_params_raises(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    with pytest.raises(ValidationError):
        runner.submit(_ctx(tmp_path), operation="demo.echo", params={})  # missing 'message'


def test_submit_persists_immediately(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    record = runner.submit(_ctx(tmp_path), operation="demo.echo", params={"message": "hi"})
    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    loaded = repo.get("acme", record.job_id)
    assert loaded.state is JobState.QUEUED


def test_submit_audit_event_id_present_in_persisted_record(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    record = runner.submit(_ctx(tmp_path), operation="demo.echo", params={"message": "hi"})
    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    loaded = repo.get("acme", record.job_id)
    assert len(loaded.audit_event_ids) == 1  # would be 0 if save() ran before audit


# ---------- run: success ----------

def test_run_completes_successfully(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "hi"})
    result = runner.run("acme", record.job_id)
    assert result.state is JobState.COMPLETED
    assert result.result_data == {"echo": "hi", "client_slug": "acme"}
    assert result.started_at is not None
    assert result.finished_at is not None


def test_run_idempotent_on_completed(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "hi"})
    r1 = runner.run("acme", record.job_id)
    r2 = runner.run("acme", record.job_id)
    assert r1.job_id == r2.job_id
    assert r2.state is JobState.COMPLETED


def test_run_idempotent_does_not_append_audit_event(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    record = runner.submit(ctx, operation="demo.echo", params={"message": "hi"})
    runner.run("acme", record.job_id)
    events_after_first = len(mem.read_audit_events("acme"))
    runner.run("acme", record.job_id)  # idempotent no-op
    events_after_second = len(mem.read_audit_events("acme"))
    assert events_after_first == events_after_second


def test_run_double_execution_protection(tmp_path: Path) -> None:
    """Running a COMPLETED job twice does not re-execute the handler —
    this is the check-then-act guard the design explicitly does NOT
    claim is safe across concurrent processes (see runner docstring)."""
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "first"})
    r1 = runner.run("acme", record.job_id)
    assert r1.result_data["echo"] == "first"
    r2 = runner.run("acme", record.job_id)
    assert r2.result_data["echo"] == "first"  # unchanged — not re-run


# ---------- run: failure ----------

def test_run_failure_produces_structured_error(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.fail", params={"reason": "boom"})
    result = runner.run("acme", record.job_id)
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_INPUT
    assert result.error.message == "boom"


def test_run_handler_exception_maps_to_internal_error(tmp_path: Path) -> None:
    def _boom_handler(ctx, params):
        raise RuntimeError("unexpected crash")

    class _Params(__import__("pydantic").BaseModel):
        pass

    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.crash", params_model=_Params, handler=_boom_handler,
        risk_class=JobRiskClass.LOW, description="crashes",
    ))
    runner = _runner(tmp_path, registry=reg)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="test.crash", params={})
    result = runner.run("acme", record.job_id)
    assert result.state is JobState.FAILED
    assert result.error.code is ErrorCode.INTERNAL
    assert "RuntimeError" in result.error.message


def test_run_never_crashes_the_runner_process(tmp_path: Path) -> None:
    """A handler exception is caught — the caller gets a FAILED record,
    never a propagated traceback."""
    def _boom_handler(ctx, params):
        raise ValueError("boom")

    class _Params(__import__("pydantic").BaseModel):
        pass

    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.crash2", params_model=_Params, handler=_boom_handler,
        risk_class=JobRiskClass.LOW, description="crashes",
    ))
    runner = _runner(tmp_path, registry=reg)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="test.crash2", params={})
    # Must not raise.
    result = runner.run("acme", record.job_id)
    assert result.state is JobState.FAILED


# ---------- run: waiting_approval ----------

def test_run_produces_waiting_approval(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.needs_approval", params={"reason": "risky"})
    result = runner.run("acme", record.job_id)
    assert result.state is JobState.WAITING_APPROVAL
    assert result.approval_reason == "risky"


def test_waiting_approval_status_read_from_outcome_not_inferred(tmp_path: Path) -> None:
    """The handler's JobOutcome.status is what drives the transition —
    not any string match on data/messages."""
    def _handler(ctx, params):
        return JobOutcome(
            status=JobOutcomeStatus.WAITING_APPROVAL,
            data={"note": "this text does not say the magic word"},
            approval_reason="explicit status field only",
        )

    class _Params(__import__("pydantic").BaseModel):
        pass

    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.wait", params_model=_Params, handler=_handler,
        risk_class=JobRiskClass.LOW, description="waits",
    ))
    runner = _runner(tmp_path, registry=reg)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="test.wait", params={})
    result = runner.run("acme", record.job_id)
    assert result.state is JobState.WAITING_APPROVAL


# ---------- run: illegal states ----------

def test_run_on_running_job_raises(tmp_path: Path) -> None:
    """A job stuck in RUNNING (e.g. from a crashed prior run) is not
    silently taken over."""
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    record.state = JobState.RUNNING
    repo.save(record)
    with pytest.raises(JobTransitionError):
        runner.run("acme", record.job_id)


def test_run_on_failed_job_raises(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.fail", params={"reason": "x"})
    runner.run("acme", record.job_id)  # -> FAILED
    with pytest.raises(JobTransitionError):
        runner.run("acme", record.job_id)


def test_run_missing_job_raises_entity_not_found(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    with pytest.raises(EntityNotFound):
        runner.run("acme", "does-not-exist")


def test_run_corrupted_job_raises_persistence_error(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    path = tmp_path / "mem" / "acme" / "job" / f"{record.job_id}.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(JobPersistenceError):
        runner.run("acme", record.job_id)


# ---------- cancel ----------

def test_cancel_queued(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    result = runner.cancel("acme", record.job_id)
    assert result.state is JobState.CANCELLED
    assert result.finished_at is not None


def test_cancel_waiting_approval(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.needs_approval", params={"reason": "x"})
    runner.run("acme", record.job_id)  # -> WAITING_APPROVAL
    result = runner.cancel("acme", record.job_id)
    assert result.state is JobState.CANCELLED


def test_cancel_idempotent_on_cancelled(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    r1 = runner.cancel("acme", record.job_id)
    r2 = runner.cancel("acme", record.job_id)
    assert r1.state is JobState.CANCELLED
    assert r2.state is JobState.CANCELLED


def test_cancel_running_raises_with_documented_reason(tmp_path: Path) -> None:
    """RUNNING cannot be cancelled by the inline runner — the limitation
    is documented, never simulated."""
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    record.state = JobState.RUNNING
    repo.save(record)
    with pytest.raises(JobTransitionError, match="synchronously"):
        runner.cancel("acme", record.job_id)


def test_cancel_completed_raises(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    runner.run("acme", record.job_id)
    with pytest.raises(JobTransitionError):
        runner.cancel("acme", record.job_id)


def test_cancel_requested_flag_has_no_effect_on_inline_runner(tmp_path: Path) -> None:
    """Functional pin (a textual source-grep is too fragile — this repo's
    own docstrings legitimately mention the field name in prose): setting
    cancel_requested=True on a RUNNING job changes nothing.
    InlineJobRunner still refuses to cancel it with the same
    JobTransitionError as when the flag is False."""
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    record.state = JobState.RUNNING
    record.cancel_requested = True
    repo.save(record)
    with pytest.raises(JobTransitionError, match="synchronously"):
        runner.cancel("acme", record.job_id)


# ---------- audit trail ----------

def test_audit_events_recorded_for_full_lifecycle(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    runner.run("acme", record.job_id)
    events = mem.read_audit_events("acme")
    actions = [e.payload["job"]["action"] for e in events]
    assert actions == ["submitted", "started", "completed"]


def test_audit_event_id_is_real_event_id(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    result = runner.run("acme", record.job_id)
    events = mem.read_audit_events("acme")
    assert result.audit_event_ids[-1] == events[-1].event_id
    assert result.audit_event_ids[-1] != events[-1].hash


def test_audit_records_from_and_to_state(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx = _ctx(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    record = runner.submit(ctx, operation="demo.echo", params={"message": "x"})
    runner.run("acme", record.job_id)
    events = mem.read_audit_events("acme")
    started_event = next(e for e in events if e.payload["job"]["action"] == "started")
    assert started_event.payload["job"]["from_state"] == "queued"
    assert started_event.payload["job"]["to_state"] == "running"


# ---------- multi-tenant isolation ----------

def test_run_isolated_per_tenant(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    ctx_acme = _ctx(tmp_path, "acme")
    ctx_other = _ctx(tmp_path, "other-client")
    j_acme = runner.submit(ctx_acme, operation="demo.echo", params={"message": "a"})
    j_other = runner.submit(ctx_other, operation="demo.echo", params={"message": "b"})
    runner.run("acme", j_acme.job_id)
    with pytest.raises(EntityNotFound):
        runner.run("other-client", j_acme.job_id)  # wrong tenant for this job_id
    result = runner.run("other-client", j_other.job_id)
    assert result.result_data["echo"] == "b"


# ---------- no argparse dependency ----------

def test_runner_module_does_not_import_argparse() -> None:
    from core.jobs import runner as runner_module

    source = inspect.getsource(runner_module)
    assert "import argparse" not in source
    assert "from argparse" not in source


def test_registry_module_does_not_import_argparse() -> None:
    from core.jobs import registry as registry_module

    source = inspect.getsource(registry_module)
    assert "import argparse" not in source


def test_models_module_does_not_import_argparse() -> None:
    from core.jobs import models as models_module

    source = inspect.getsource(models_module)
    assert "import argparse" not in source
