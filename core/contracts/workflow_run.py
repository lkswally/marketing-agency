"""WorkflowRunSummary — end-of-run record for a workflow execution.

Contract: ``workflow-run.v1``

A WorkflowRunSummary is the artifact a future dispatcher emits when a workflow
finishes (or is cancelled). It references envelopes and gate results by id
rather than embedding them, keeping the summary small enough to keep in memory.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.domain.base import DomainModel, new_id, validate_slug

from .envelope import EnvelopeStatus
from .phase_gate import PhaseGateResult

WORKFLOW_RUN_VERSION = "workflow-run.v1"


class WorkflowRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}
)
_FAILED_ENVELOPE_STATUSES = frozenset({EnvelopeStatus.FALLIDO, EnvelopeStatus.FAIL})


class StepResult(DomainModel):
    """Outcome of one step within a workflow run."""

    step_id: str = Field(min_length=1, max_length=200)
    agent: str = Field(min_length=1, max_length=200)
    status: EnvelopeStatus
    envelope_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    retries: int = Field(default=0, ge=0)
    notes: str | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("step timestamps must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _finished_after_started(self) -> StepResult:
        if self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        return self


class WorkflowRunSummary(DomainModel):
    """End-of-run summary."""

    contract_version: Literal["workflow-run.v1"] = WORKFLOW_RUN_VERSION
    run_id: str = Field(default_factory=new_id)
    workflow_name: str = Field(min_length=1, max_length=200)
    client_slug: str = Field(min_length=2, max_length=64)
    started_at: datetime
    finished_at: datetime | None = None
    status: WorkflowRunStatus
    steps: list[StepResult] = Field(default_factory=list)
    gate_results: list[PhaseGateResult] = Field(default_factory=list)
    envelope_refs: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("run timestamps must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _date_order(self) -> WorkflowRunSummary:
        if self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        return self

    @model_validator(mode="after")
    def _terminal_requires_finished_at(self) -> WorkflowRunSummary:
        if self.status in _TERMINAL_STATUSES and self.finished_at is None:
            raise ValueError(
                f"status={self.status.value} (terminal) requires finished_at"
            )
        return self

    @model_validator(mode="after")
    def _succeeded_has_no_failed_steps(self) -> WorkflowRunSummary:
        if self.status is WorkflowRunStatus.SUCCEEDED:
            bad = [s.step_id for s in self.steps if s.status in _FAILED_ENVELOPE_STATUSES]
            if bad:
                raise ValueError(
                    f"status=succeeded cannot contain failed steps: {bad}"
                )
        return self

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration in seconds, or None if not finished."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()
