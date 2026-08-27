"""Job application service (MKT-11C).

Thin wrapper: translates :class:`~core.jobs.InlineJobRunner` calls and
exceptions into :class:`~core.application.result.OperationResult` — the
same contract every other service in this package returns. No business
logic beyond that translation lives here; the state machine and
persistence rules live in :mod:`core.jobs`.
"""

from __future__ import annotations

from pydantic import ValidationError

from core.jobs import (
    InlineJobRunner,
    JobPersistenceError,
    JobRegistry,
    JobState,
    JobTransitionError,
    UnknownOperationError,
)
from core.jobs.repository import JobRepository
from core.memory import EntityNotFound, JsonFileMemory

from ..context import OperationContext
from ..policies import check_can_execute_job
from ..result import ErrorCode, OperationError, OperationResult, OperationStatus, OperationWarning


def _runner_for(ctx: OperationContext, registry: JobRegistry | None) -> InlineJobRunner:
    memory = JsonFileMemory(ctx.root)
    return InlineJobRunner(memory, root=ctx.root, registry=registry)


def submit_job(
    ctx: OperationContext,
    *,
    operation: str,
    params: dict,
    registry: JobRegistry | None = None,
) -> OperationResult:
    """Validate and persist a new QUEUED job. Does not execute it — call
    :func:`run_job` (or :func:`submit_and_run`) separately."""
    perm_error = check_can_execute_job(ctx)
    if perm_error is not None:
        return perm_error

    runner = _runner_for(ctx, registry)
    try:
        record = runner.submit(ctx, operation=operation, params=params)
    except UnknownOperationError as e:
        return OperationResult.error_result(
            code=ErrorCode.UNKNOWN_OPERATION, message=str(e),
        )
    except ValidationError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=f"invalid params for operation {operation!r}: {e}",
        )
    return OperationResult.ok_result(
        data=record, audit_event_id=record.audit_event_ids[-1],
    )


def run_job(
    ctx: OperationContext, *, job_id: str, registry: JobRegistry | None = None,
) -> OperationResult:
    """Execute a QUEUED job. Idempotent on COMPLETED (ok + warning, no
    re-execution, no new audit event)."""
    perm_error = check_can_execute_job(ctx)
    if perm_error is not None:
        return perm_error

    runner = _runner_for(ctx, registry)
    try:
        before = JobRepository(JsonFileMemory(ctx.root)).get(ctx.client_slug, job_id)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no job {job_id!r} for client {ctx.client_slug!r}",
        )
    except JobPersistenceError as e:
        return OperationResult.error_result(
            code=ErrorCode.PERSISTENCE_ERROR, message=str(e),
        )

    was_completed = before.state is JobState.COMPLETED
    try:
        record = runner.run(ctx.client_slug, job_id)
    except JobTransitionError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_STATE_TRANSITION, message=str(e),
        )

    if was_completed:
        return OperationResult.ok_result(
            data=record,
            warnings=[OperationWarning(
                code="already_completed",
                message="job is already COMPLETED — not re-executed",
            )],
        )

    audit_id = record.audit_event_ids[-1] if record.audit_event_ids else None
    if record.state is JobState.FAILED:
        # Deliberately NOT error_result() — that constructor never sets
        # `data`, and the CLI needs the failed JobRecord (to print it and
        # to select ExitCode.JOB_FAILED) alongside the structured error.
        code = record.error.code if record.error else ErrorCode.INTERNAL
        message = record.error.message if record.error else "job failed"
        return OperationResult(
            status=OperationStatus.ERROR,
            data=record,
            error=OperationError(code=code, message=message),
            audit_event_id=audit_id,
        )
    return OperationResult.ok_result(data=record, audit_event_id=audit_id)


def show_job(ctx: OperationContext, *, job_id: str) -> OperationResult:
    """Load one job by id. Read-only — no permission check (mirrors
    approvals' show/list posture, MKT-11B)."""
    try:
        record = JobRepository(JsonFileMemory(ctx.root)).get(ctx.client_slug, job_id)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no job {job_id!r} for client {ctx.client_slug!r}",
        )
    except JobPersistenceError as e:
        return OperationResult.error_result(
            code=ErrorCode.PERSISTENCE_ERROR, message=str(e),
        )
    return OperationResult.ok_result(data=record)


def list_jobs(
    ctx: OperationContext,
    *,
    state: str | None = None,
    operation: str | None = None,
    limit: int | None = None,
) -> OperationResult:
    """List jobs for one tenant, newest first. Read-only."""
    records = JobRepository(JsonFileMemory(ctx.root)).list_for_client(
        ctx.client_slug, state=state, operation=operation, limit=limit,
    )
    return OperationResult.ok_result(data=records)


def cancel_job(
    ctx: OperationContext, *, job_id: str, registry: JobRegistry | None = None,
) -> OperationResult:
    """Cancel a QUEUED or WAITING_APPROVAL job. Idempotent on CANCELLED.
    A RUNNING job cannot be cancelled by the inline runner — see
    :meth:`core.jobs.InlineJobRunner.cancel`."""
    perm_error = check_can_execute_job(ctx)
    if perm_error is not None:
        return perm_error

    runner = _runner_for(ctx, registry)
    try:
        before = JobRepository(JsonFileMemory(ctx.root)).get(ctx.client_slug, job_id)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no job {job_id!r} for client {ctx.client_slug!r}",
        )
    except JobPersistenceError as e:
        return OperationResult.error_result(
            code=ErrorCode.PERSISTENCE_ERROR, message=str(e),
        )

    was_cancelled = before.state is JobState.CANCELLED
    try:
        record = runner.cancel(ctx.client_slug, job_id)
    except JobTransitionError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_STATE_TRANSITION, message=str(e),
        )

    if was_cancelled:
        return OperationResult.ok_result(
            data=record,
            warnings=[OperationWarning(
                code="already_cancelled",
                message="job is already CANCELLED — no state change",
            )],
        )
    audit_id = record.audit_event_ids[-1] if record.audit_event_ids else None
    return OperationResult.ok_result(data=record, audit_event_id=audit_id)


__all__ = [
    "cancel_job",
    "list_jobs",
    "run_job",
    "show_job",
    "submit_job",
]
