"""Tests for the jobs application service (MKT-11C)."""

from __future__ import annotations

from pathlib import Path

from core.application import OperationContext, OperationRole
from core.application.result import ErrorCode
from core.application.services import jobs
from core.jobs.models import JobState


def _ctx(
    tmp_path: Path, client: str = "acme", role: OperationRole = OperationRole.OPERATOR,
) -> OperationContext:
    return OperationContext(client_slug=client, root=tmp_path / "mem", role=role)


# ---------- submit ----------

def test_submit_ok(tmp_path: Path) -> None:
    result = jobs.submit_job(_ctx(tmp_path), operation="demo.echo", params={"message": "hi"})
    assert result.ok
    assert result.data.state is JobState.QUEUED
    assert result.audit_event_id is not None


def test_submit_unknown_operation(tmp_path: Path) -> None:
    result = jobs.submit_job(_ctx(tmp_path), operation="nope", params={})
    assert not result.ok
    assert result.error.code is ErrorCode.UNKNOWN_OPERATION


def test_submit_invalid_params(tmp_path: Path) -> None:
    result = jobs.submit_job(_ctx(tmp_path), operation="demo.echo", params={})
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_submit_permission_denied_for_viewer(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, role=OperationRole.VIEWER)
    result = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


def test_submit_permission_denied_for_analyst(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, role=OperationRole.ANALYST)
    result = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


def test_submit_allowed_for_approver(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, role=OperationRole.APPROVER)
    result = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    assert result.ok


def test_submit_allowed_for_admin(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, role=OperationRole.ADMIN)
    result = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    assert result.ok


# ---------- run ----------

def test_run_ok(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    result = jobs.run_job(ctx, job_id=submitted.data.job_id)
    assert result.ok
    assert result.data.state is JobState.COMPLETED


def test_run_idempotent_on_completed_returns_warning(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    jobs.run_job(ctx, job_id=submitted.data.job_id)
    r2 = jobs.run_job(ctx, job_id=submitted.data.job_id)
    assert r2.ok
    assert r2.warnings


def test_run_not_found(tmp_path: Path) -> None:
    result = jobs.run_job(_ctx(tmp_path), job_id="nope")
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_run_failed_job_returns_error_with_data(tmp_path: Path) -> None:
    """The FAILED-job result must carry `data` alongside `error` so the
    CLI can print the job record and pick ExitCode.JOB_FAILED."""
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.fail", params={"reason": "boom"})
    result = jobs.run_job(ctx, job_id=submitted.data.job_id)
    assert not result.ok
    assert result.data is not None
    assert result.data.state is JobState.FAILED
    assert result.error.message == "boom"


def test_run_permission_denied_for_viewer(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    viewer_ctx = _ctx(tmp_path, role=OperationRole.VIEWER)
    result = jobs.run_job(viewer_ctx, job_id=submitted.data.job_id)
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


def test_run_waiting_approval(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.needs_approval", params={"reason": "x"})
    result = jobs.run_job(ctx, job_id=submitted.data.job_id)
    assert result.ok
    assert result.data.state is JobState.WAITING_APPROVAL


# ---------- show ----------

def test_show_ok(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    result = jobs.show_job(ctx, job_id=submitted.data.job_id)
    assert result.ok
    assert result.data.job.job_id == submitted.data.job_id
    # job-execution-robustness: a freshly-submitted (QUEUED) job's
    # liveness question doesn't apply.
    assert result.data.liveness.value == "not_applicable"


def test_show_not_found(tmp_path: Path) -> None:
    result = jobs.show_job(_ctx(tmp_path), job_id="nope")
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_show_no_permission_check(tmp_path: Path) -> None:
    """Read operations are unrestricted, mirroring approvals show/list."""
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    viewer_ctx = _ctx(tmp_path, role=OperationRole.VIEWER)
    result = jobs.show_job(viewer_ctx, job_id=submitted.data.job_id)
    assert result.ok


# ---------- list ----------

def test_list_ok(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    jobs.submit_job(ctx, operation="demo.echo", params={"message": "a"})
    jobs.submit_job(ctx, operation="demo.echo", params={"message": "b"})
    result = jobs.list_jobs(ctx)
    assert result.ok
    assert len(result.data) == 2
    assert {v.job.operation for v in result.data} == {"demo.echo"}


def test_list_empty(tmp_path: Path) -> None:
    result = jobs.list_jobs(_ctx(tmp_path))
    assert result.ok
    assert result.data == []


def test_list_filters_by_state(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    j1 = jobs.submit_job(ctx, operation="demo.echo", params={"message": "a"})
    jobs.submit_job(ctx, operation="demo.echo", params={"message": "b"})
    jobs.run_job(ctx, job_id=j1.data.job_id)
    result = jobs.list_jobs(ctx, state="completed")
    assert len(result.data) == 1


# ---------- cancel ----------

def test_cancel_queued(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    result = jobs.cancel_job(ctx, job_id=submitted.data.job_id)
    assert result.ok
    assert result.data.state is JobState.CANCELLED


def test_cancel_idempotent(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    jobs.cancel_job(ctx, job_id=submitted.data.job_id)
    r2 = jobs.cancel_job(ctx, job_id=submitted.data.job_id)
    assert r2.ok
    assert r2.warnings


def test_cancel_running_returns_invalid_transition(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    from core.jobs.repository import JobRepository
    from core.memory import JsonFileMemory

    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    record = repo.get("acme", submitted.data.job_id)
    record.state = JobState.RUNNING
    repo.save(record)
    result = jobs.cancel_job(ctx, job_id=submitted.data.job_id)
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_STATE_TRANSITION


def test_cancel_not_found(tmp_path: Path) -> None:
    result = jobs.cancel_job(_ctx(tmp_path), job_id="nope")
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_cancel_permission_denied(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    submitted = jobs.submit_job(ctx, operation="demo.echo", params={"message": "hi"})
    viewer_ctx = _ctx(tmp_path, role=OperationRole.VIEWER)
    result = jobs.cancel_job(viewer_ctx, job_id=submitted.data.job_id)
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


# ---------- multi-tenant isolation ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    ctx_acme = _ctx(tmp_path, "acme")
    ctx_other = _ctx(tmp_path, "other-client")
    jobs.submit_job(ctx_acme, operation="demo.echo", params={"message": "a"})
    jobs.submit_job(ctx_other, operation="demo.echo", params={"message": "b"})
    assert len(jobs.list_jobs(ctx_acme).data) == 1
    assert len(jobs.list_jobs(ctx_other).data) == 1


# ---------- determinism ----------

def test_submit_deterministic_state(tmp_path: Path) -> None:
    ctx1 = _ctx(tmp_path, "acme")
    ctx2 = OperationContext(client_slug="acme", root=tmp_path / "mem2")
    r1 = jobs.submit_job(ctx1, operation="demo.echo", params={"message": "hi"})
    r2 = jobs.submit_job(ctx2, operation="demo.echo", params={"message": "hi"})
    assert r1.data.state == r2.data.state
    assert r1.data.operation == r2.data.operation
