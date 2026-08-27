"""Job contract and state machine (MKT-11C).

A :class:`JobRecord` is the persisted unit of long-running work. One record
per job, one file per record — **no singleton**, full history preserved.

**Concurrency posture (documented, not simulated).** ``memory.v1`` guarantees
single-process sequential use only (P-1D.3). The double-execution protection
in this module is a *check-then-act state guard*, which protects the real CLI
case (sequential invocations). It does **not** protect two concurrent
processes: both could read ``QUEUED`` and both execute. MKT-11F (advisory
per-client lock) is the scheduled fix. Nothing here claims atomicity it
cannot deliver.

**No progress field.** :class:`InlineJobRunner` is synchronous, so no observer
can read an intermediate value while a job runs. A percentage would be
fiction, so none is stored.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.application.result import ErrorCode
from core.domain.base import new_id, utcnow, validate_slug

JOB_KIND = "job"
"""Memory kind. Matches ``[a-z][a-z0-9_]{0,63}``."""

JOB_CONTRACT_VERSION = "job.v1"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"
    """Reserved for operations that pause for a human decision. No
    production operation emits it in MKT-11C — the demo operation
    ``demo.needs_approval`` exercises it so the transition is covered by
    tests rather than being dead code. Operational resume is MKT-11D."""


TERMINAL_STATES: frozenset[JobState] = frozenset({
    JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED,
})

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
    JobState.RUNNING: frozenset({
        JobState.COMPLETED, JobState.FAILED, JobState.WAITING_APPROVAL,
    }),
    JobState.WAITING_APPROVAL: frozenset({
        JobState.QUEUED,      # resume path — machine only; no service in 11C
        JobState.CANCELLED,
    }),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def can_transition(current: JobState, target: JobState) -> bool:
    """True when ``current -> target`` is a permitted transition."""
    return target in ALLOWED_TRANSITIONS[current]


class JobError(BaseModel):
    """Structured failure attached to a FAILED job."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=2000)]


class JobOutcomeStatus(StrEnum):
    """What a handler tells the runner. Deliberately separate from
    :class:`~core.application.result.OperationStatus`: an operation result
    is the *service → caller* contract, while an outcome is the
    *handler → runner* contract and must be able to express
    ``WAITING_APPROVAL``, which is not an operation status."""

    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class JobOutcome(BaseModel):
    """A handler's structured return value.

    ``WAITING_APPROVAL`` is signalled by ``status``, never inferred from a
    message, a warning, or any string content.
    """

    model_config = ConfigDict(frozen=True)

    status: JobOutcomeStatus
    data: dict[str, Any] | None = None
    result_ref: str | None = Field(default=None, max_length=200)
    """Pointer to an entity or artifact the operation produced."""
    error: JobError | None = None
    approval_reason: str | None = Field(default=None, max_length=1000)
    """Why a human decision is required. Only meaningful when
    ``status is WAITING_APPROVAL``."""

    @classmethod
    def completed(
        cls, *, data: dict[str, Any] | None = None, result_ref: str | None = None,
    ) -> JobOutcome:
        return cls(
            status=JobOutcomeStatus.COMPLETED, data=data, result_ref=result_ref,
        )

    @classmethod
    def failed(cls, *, code: ErrorCode, message: str) -> JobOutcome:
        return cls(
            status=JobOutcomeStatus.FAILED,
            error=JobError(code=code, message=message),
        )

    @classmethod
    def waiting_approval(cls, *, reason: str) -> JobOutcome:
        return cls(
            status=JobOutcomeStatus.WAITING_APPROVAL, approval_reason=reason,
        )


class JobRecord(BaseModel):
    """One persisted job. Mutable by design — the runner advances it through
    the state machine and re-persists at every transition."""

    model_config = ConfigDict(validate_assignment=True)

    contract_version: str = JOB_CONTRACT_VERSION
    job_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    operation: Annotated[str, Field(min_length=1, max_length=120)]
    state: JobState = JobState.QUEUED

    params: dict[str, Any] = Field(default_factory=dict)
    """Validated against the operation's ``params_model`` before the record
    is created. Fields the operation declared sensitive are redacted before
    persistence — see :mod:`core.jobs.repository`."""

    actor_id: str = "unknown"
    role: str = "operator"
    source: str = "cli"
    correlation_id: str = Field(default_factory=new_id)

    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    attempt: int = Field(default=1, ge=1)
    """No automatic retries in MKT-11C. The field exists so a future retry
    policy does not require a contract bump."""

    result_data: dict[str, Any] | None = None
    result_ref: str | None = Field(default=None, max_length=200)
    error: JobError | None = None
    approval_reason: str | None = Field(default=None, max_length=1000)

    audit_event_ids: list[str] = Field(default_factory=list)

    cancel_requested: bool = False
    """Reserved for future non-inline runners. :class:`InlineJobRunner`
    never reads it — with synchronous execution no other actor can set it
    and have it observed, so honouring it would be theatre."""

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at", "started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


__all__ = [
    "ALLOWED_TRANSITIONS",
    "JOB_CONTRACT_VERSION",
    "JOB_KIND",
    "TERMINAL_STATES",
    "JobError",
    "JobOutcome",
    "JobOutcomeStatus",
    "JobRecord",
    "JobState",
    "can_transition",
]
