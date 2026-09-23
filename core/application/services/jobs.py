"""Job application service (MKT-11C).

Thin wrapper: translates :class:`~core.jobs.InlineJobRunner` calls and
exceptions into :class:`~core.application.result.OperationResult` — the
same contract every other service in this package returns. No business
logic beyond that translation lives here; the state machine and
persistence rules live in :mod:`core.jobs`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from core.jobs import (
    InlineJobRunner,
    JobPersistenceError,
    JobRecord,
    JobRegistry,
    JobState,
    JobTransitionError,
    UnknownOperationError,
    default_registry,
)
from core.jobs.liveness import LivenessStatus, probe_liveness
from core.jobs.operations.campaign import register_campaign_operations
from core.jobs.repository import JobRepository
from core.memory import EntityNotFound, JsonFileMemory

from ..context import OperationContext
from ..policies import check_can_execute_job
from ..result import ErrorCode, OperationError, OperationResult, OperationStatus, OperationWarning


class JobRecordView(BaseModel):
    """``show_job``/``list_jobs`` response shape: the persisted
    :class:`~core.jobs.models.JobRecord` plus a derived, never-persisted
    liveness observation (job-execution-robustness). ``liveness`` is
    computed fresh on every read — it is not, and must never become, a
    field on ``JobRecord`` itself (that would make ``job.v1`` claim a
    real-time property no static, persisted contract can honestly hold)."""

    model_config = ConfigDict(frozen=True)

    job: JobRecord
    liveness: LivenessStatus


def _with_liveness(ctx: OperationContext, record: JobRecord) -> JobRecordView:
    return JobRecordView(job=record, liveness=probe_liveness(ctx.root, record))

# MKT-11D — registered here, not in core/jobs/__init__.py, to avoid a
# circular import: campaign.run's handler depends on
# core.application.services.campaign_run, and this very module
# (core.application.services.jobs) is what core.application.services
# eagerly imported before the MKT-11D fix that removed that eager
# aggregation (see core/application/services/__init__.py). Importing
# core.jobs.operations.campaign here is safe regardless of import order —
# see the longer explanation in core/jobs/__init__.py.
register_campaign_operations(default_registry)


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
    approvals' show/list posture, MKT-11B). ``data`` is a
    :class:`JobRecordView` (the record plus a derived, never-persisted
    ``liveness`` observation — see :mod:`core.jobs.liveness`), not a bare
    ``JobRecord``, since job-execution-robustness."""
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
    return OperationResult.ok_result(data=_with_liveness(ctx, record))


def list_jobs(
    ctx: OperationContext,
    *,
    state: str | None = None,
    operation: str | None = None,
    limit: int | None = None,
) -> OperationResult:
    """List jobs for one tenant, newest first. Read-only. ``data`` is a
    ``list[JobRecordView]`` — see :func:`show_job`."""
    records = JobRepository(JsonFileMemory(ctx.root)).list_for_client(
        ctx.client_slug, state=state, operation=operation, limit=limit,
    )
    return OperationResult.ok_result(data=[_with_liveness(ctx, r) for r in records])


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
