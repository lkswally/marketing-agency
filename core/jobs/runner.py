"""InlineJobRunner — synchronous, in-process job execution (MKT-11C).

``submit`` creates a QUEUED record. ``run`` drives it through
``QUEUED -> RUNNING -> {COMPLETED, FAILED, WAITING_APPROVAL}``, persisting
and auditing at every transition. No thread, no process, no external
queue — this runner IS the execution, on the calling thread, right now.

**Execution lock (job-execution-robustness).** ``run()`` holds a per-job
:class:`~core.memory.filelock.FileLock` for its entire duration —
acquired *before* the authoritative state is (re-)read, released in a
``finally`` no matter how execution ends. This closes the
check-then-act race a purely in-memory/sequential guard cannot: two
concurrent callers (threads or separate OS processes on this host) racing
``run()`` on the same ``job_id`` now have exactly one winner; the other(s)
get a structured :class:`JobTransitionError`, never a duplicate handler
execution. See ``core/memory/filelock.py`` for exactly what this
mechanism guarantees (single host, real filesystem) and does not
(distributed / network-filesystem safety is NOT claimed).

The lock represents *active execution*, not ownership of the job until a
human decision — it is released the moment ``run()`` returns, including
on a ``WAITING_APPROVAL`` outcome. A second ``run()`` call on that same
job afterwards is still rejected, but by the state machine (the record is
no longer ``QUEUED``), not by the lock — lock lifecycle and state-machine
enforcement are deliberately two separate mechanisms.

Never imports ``argparse`` — this module is a pure application-layer
component; the CLI adapter is the only place argument parsing happens.
"""

from __future__ import annotations

from pathlib import Path

from core.application.context import OperationContext
from core.application.result import ErrorCode
from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory
from core.memory.filelock import FileLock

from .models import JobError, JobOutcome, JobOutcomeStatus, JobRecord, JobState, can_transition
from .registry import JobRegistry, UnknownOperationError, default_registry
from .repository import JobPersistenceError, JobRepository, sanitize_params

_ACTOR = "job_runner"
_LOCKS_DIRNAME = "_locks"


def job_lock_path(root: Path, client_slug: str, job_id: str) -> Path:
    """The execution-lock path for one job. A free function (not a method)
    so :mod:`core.jobs.liveness` can build the identical path for a
    read-only probe without needing a live :class:`InlineJobRunner`
    instance — same single source of truth either way."""
    return root / client_slug / _LOCKS_DIRNAME / f"job_{job_id}.lock"


class JobTransitionError(RuntimeError):
    """Raised when a caller asks the runner to advance a job past a
    transition the state machine forbids, OR when a concurrent ``run()``
    on the same job lost the execution-lock race. Callers map this to
    ``ErrorCode.INVALID_STATE_TRANSITION`` — never let it propagate raw."""


class InlineJobRunner:
    """Submits and executes jobs synchronously on the calling thread."""

    def __init__(
        self, memory: Memory, *, root: Path, registry: JobRegistry | None = None,
    ) -> None:
        self._memory = memory
        self._root = root
        self._repo = JobRepository(memory)
        self._registry = registry or default_registry

    def _job_lock(self, client_slug: str, job_id: str) -> FileLock:
        return FileLock(job_lock_path(self._root, client_slug, job_id))

    # ---------- submit ----------

    def submit(self, ctx: OperationContext, *, operation: str, params: dict) -> JobRecord:
        """Validate ``params`` against the operation's contract, sanitize
        sensitive fields, and persist a new QUEUED job.

        Raises:
            UnknownOperationError: no spec registered for ``operation``.
            pydantic.ValidationError: ``params`` fails the spec's
                ``params_model``.
        """
        spec = self._registry.resolve(operation)  # UnknownOperationError propagates
        validated = spec.params_model.model_validate(params)
        clean_params = sanitize_params(
            validated.model_dump(mode="json"), spec.sensitive_param_fields,
        )
        record = JobRecord(
            client_slug=ctx.client_slug,
            operation=operation,
            state=JobState.QUEUED,
            params=clean_params,
            actor_id=ctx.actor_id,
            role=ctx.role.value,
            source=ctx.source.value,
            correlation_id=ctx.correlation_id,
        )
        self._audit(record, action="submitted", from_state=None)
        self._repo.save(record)
        return record

    # ---------- run ----------

    def run(self, client_slug: str, job_id: str) -> JobRecord:
        """Execute a QUEUED job. Idempotent on COMPLETED (returns the
        existing record, no re-execution, no new audit event). Any other
        non-QUEUED state raises :class:`JobTransitionError`.

        Holds this job's execution lock for the full call. A concurrent
        caller that loses the lock race gets ``JobTransitionError``
        immediately — it never reads stale state, never executes the
        handler, never duplicates work. See the module docstring.
        """
        # No pre-lock read of any kind is used to decide anything here —
        # acquire -> reload -> transition, strictly in that order, so the
        # execution decision is always made against state read AFTER
        # exclusivity is held, never before.
        lock = self._job_lock(client_slug, job_id)
        if not lock.try_acquire():
            raise JobTransitionError(
                f"cannot run job {job_id!r}: another execution is already "
                "in progress (execution lock held by another caller)"
            )
        try:
            # Authoritative re-read, now that we hold exclusivity.
            record = self._load(client_slug, job_id)

            if record.state is JobState.COMPLETED:
                return record  # another caller finished it while we waited

            if record.state is not JobState.QUEUED:
                raise JobTransitionError(
                    f"cannot run job {job_id!r} in state {record.state.value!r} "
                    "— only QUEUED jobs can be run"
                )

            self._transition(record, JobState.RUNNING, action="started")
            record.started_at = utcnow()
            # We hold this job's execution lock right now — mark the
            # record as lock-protected so a later liveness probe (see
            # core/jobs/liveness.py) can trust "lock is free" as a real
            # stale-crash signal for it, instead of treating it as an
            # unknowable legacy RUNNING record.
            record.lock_protected = True
            self._repo.save(record)

            try:
                spec = self._registry.resolve(record.operation)
            except UnknownOperationError as e:
                return self._fail(record, ErrorCode.UNKNOWN_OPERATION, str(e))

            try:
                params_model = spec.params_model.model_validate(record.params)
                outcome = spec.handler(self._context_for(record), params_model)
            except Exception as e:  # noqa: BLE001 — never let a handler crash the runner
                return self._fail(record, ErrorCode.INTERNAL, f"{type(e).__name__}: {e}")

            return self._apply_outcome(record, outcome)
        finally:
            # Always released — the lock means "actively executing", not
            # "owns the job until a human decision". A WAITING_APPROVAL
            # outcome releases it exactly like COMPLETED/FAILED do.
            lock.release()

    # ---------- cancel ----------

    def cancel(self, client_slug: str, job_id: str) -> JobRecord:
        """Cancel a job that has not started running yet.

        QUEUED and WAITING_APPROVAL -> CANCELLED. Already CANCELLED is an
        idempotent no-op. RUNNING cannot be cancelled by this runner — see
        the module and JobRecord.cancel_requested docstrings: with
        synchronous, single-threaded execution there is no point at which
        a concurrent caller could set a flag and have it observed, so
        pretending to cancel a RUNNING job would be simulating a guarantee
        that does not exist. Raises :class:`JobTransitionError` for that
        case and for any other non-cancellable state.
        """
        record = self._load(client_slug, job_id)

        if record.state is JobState.CANCELLED:
            return record

        if record.state is JobState.RUNNING:
            raise JobTransitionError(
                f"cannot cancel job {job_id!r}: it is RUNNING and "
                "InlineJobRunner executes synchronously — there is no "
                "point at which cancellation could take effect. Wait for "
                "it to reach a terminal state."
            )

        if not can_transition(record.state, JobState.CANCELLED):
            raise JobTransitionError(
                f"cannot cancel job {job_id!r} in state {record.state.value!r}"
            )

        self._transition(record, JobState.CANCELLED, action="cancelled")
        record.finished_at = utcnow()
        self._repo.save(record)
        return record

    # ---------- internals ----------

    def _load(self, client_slug: str, job_id: str) -> JobRecord:
        return self._repo.get(client_slug, job_id)  # EntityNotFound / JobPersistenceError propagate

    def _context_for(self, record: JobRecord) -> OperationContext:
        return OperationContext(
            client_slug=record.client_slug,
            root=self._root,
            actor_id=record.actor_id,
            correlation_id=record.correlation_id,
            job_id=record.job_id,
        )

    def _apply_outcome(self, record: JobRecord, outcome: JobOutcome) -> JobRecord:
        if outcome.status is JobOutcomeStatus.COMPLETED:
            self._transition(record, JobState.COMPLETED, action="completed")
            record.result_data = outcome.data
            record.result_ref = outcome.result_ref
            record.finished_at = utcnow()
            self._repo.save(record)
            return record

        if outcome.status is JobOutcomeStatus.WAITING_APPROVAL:
            self._transition(record, JobState.WAITING_APPROVAL, action="waiting_approval")
            record.approval_reason = outcome.approval_reason
            # MKT-11D: a job pausing for approval may already have
            # produced real artifacts (e.g. campaign outputs up to the
            # approval stage) — carry them, never drop them.
            record.result_data = outcome.data
            record.result_ref = outcome.result_ref
            self._repo.save(record)
            return record

        # FAILED
        assert outcome.error is not None
        return self._fail(record, outcome.error.code, outcome.error.message)

    def _fail(self, record: JobRecord, code: ErrorCode, message: str) -> JobRecord:
        self._transition(record, JobState.FAILED, action="failed")
        record.error = JobError(code=code, message=message)
        record.finished_at = utcnow()
        self._repo.save(record)
        return record

    def _transition(self, record: JobRecord, target: JobState, *, action: str) -> None:
        if not can_transition(record.state, target):
            raise JobTransitionError(
                f"illegal transition for job {record.job_id!r}: "
                f"{record.state.value!r} -> {target.value!r}"
            )
        from_state = record.state
        record.state = target
        self._audit(record, action=action, from_state=from_state)

    def _audit(self, record: JobRecord, *, action: str, from_state: JobState | None) -> None:
        # append_audit_event_atomic reads the chain tail and builds the
        # event from it inside one held lock — closes the race a
        # separate last_audit_hash() read + append_audit_event() call
        # would leave open between two DIFFERENT jobs for the same
        # client appending concurrently (see core/memory/json_file.py).
        def _build(prev: str | None) -> AuditTrailEvent:
            return AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor=_ACTOR,
                occurred_at=utcnow(),
                client_slug=record.client_slug,
                payload={
                    "job": {
                        "action": action,
                        "job_id": record.job_id,
                        "operation": record.operation,
                        "from_state": from_state.value if from_state else None,
                        "to_state": record.state.value,
                        "correlation_id": record.correlation_id,
                    }
                },
                prev_hash=prev,
            )

        event = self._memory.append_audit_event_atomic(record.client_slug, _build)
        record.audit_event_ids.append(event.event_id)


# EntityNotFound / JobPersistenceError are re-raised, not wrapped, by
# `_load` — re-exported here so callers importing only the runner module
# can catch them without a second import.
__all__ = [
    "EntityNotFound",
    "InlineJobRunner",
    "JobPersistenceError",
    "JobTransitionError",
]
