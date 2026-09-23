"""CampaignRunProgress — incremental checkpoint written DURING a campaign
run (job-execution-robustness).

Why this exists, separate from ``campaign_run_summary``: the summary is
built and persisted only once, at the very end of a successful (or
cleanly-blocked/stopped) run — if the process dies partway through, the
summary never gets written at all, and there is nothing to inspect. This
entity is written incrementally, once per stage transition, so a crash
mid-pipeline still leaves a queryable record of exactly how far the run
got.

**Only written when the pipeline is driven by the job system**
(``job_id is not None`` on the owning :class:`~core.pipeline.orchestrator.PipelineOrchestrator`)
— the legacy, synchronous ``mkt run-campaign`` CLI path is byte-for-byte
unchanged, same established pattern as the ``job_id``/``correlation_id``
threading added in MKT-11D.

**Non-transactional, explicitly.** Each checkpoint write is individually
atomic (same ``JsonFileMemory.put`` every other entity uses) — there is
still no rollback, no compensation, and no way to "undo" stages 1-2 if
stage 3 fails. This entity improves detectability, diagnostics, and
reconciliation readiness. It does not make campaign execution
transactional, and no code, test, or docstring in this module should
ever imply otherwise.

**Interpreting a crash from this entity, without inventing a new
persisted job state:** if ``current_stage`` is set, that stage is absent
from both ``stages_completed`` and ``stages_skipped``, and
``last_stage_outcome`` is ``None``, the pipeline was interrupted while
that stage was in flight — combine with the owning job's
:mod:`core.jobs.liveness` result (``STALE``) to distinguish "still
genuinely running" from "crashed here". This module never reads or
writes job state itself; it only records pipeline-stage progress.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, utcnow, validate_slug
from core.memory import Memory

from .models import StageId, StageOutcome

CAMPAIGN_RUN_PROGRESS_VERSION = "campaign-run-progress.v1"
CAMPAIGN_RUN_PROGRESS_KIND = "campaign_run_progress"


class CampaignRunProgress(DomainModel):
    """One checkpoint document per job-driven campaign run, keyed by
    ``job_id`` — never a singleton, never overwritten by a different
    run's progress."""

    contract_version: Literal["campaign-run-progress.v1"] = CAMPAIGN_RUN_PROGRESS_VERSION
    job_id: str = Field(min_length=1)
    client_slug: str
    correlation_id: str | None = None

    started_at: datetime
    updated_at: datetime

    stages_completed: list[StageId] = Field(default_factory=list)
    """Stages that ran to a SUCCEEDED outcome, in the order they
    finished."""

    stages_skipped: list[StageId] = Field(default_factory=list)
    """Stages the orchestrator deliberately skipped as a batch (e.g.
    creative+visual when an approval blocks publish) — never "attempted
    and interrupted", recorded separately from stages_completed so the
    two are never conflated."""

    current_stage: StageId | None = None
    """The stage currently in flight. Set to a value the moment that
    stage starts, cleared (set back to None) the moment it reaches ANY
    terminal outcome (succeeded/failed/blocked) for that attempt — so a
    non-None value combined with that same stage being absent from
    stages_completed/stages_skipped means the run stopped mid-stage,
    whether by a controlled failure (last_stage_outcome will say so) or
    by a crash (last_stage_outcome will still be None)."""

    last_stage_outcome: Literal["succeeded", "failed", "blocked"] | None = None
    """The most recently observed terminal outcome for ``current_stage``
    at the time it was cleared — read together with ``current_stage``'s
    value from the PREVIOUS write when diagnosing a crash: by the time a
    reader observes this, current_stage has already moved on (or been
    cleared), so this field alone describes what just happened, not what
    is happening now."""

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("started_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v


class CampaignProgressTracker:
    """Stateful, per-run helper the orchestrator holds for the duration
    of one ``run()`` call. Not shared across runs, not thread-safe on its
    own (the owning job's execution lock already serializes one job's
    ``run()`` — see core/jobs/runner.py — so no additional locking is
    added here; two DIFFERENT jobs never share a
    ``CampaignRunProgress`` document, since it's keyed by job_id)."""

    def __init__(
        self, memory: Memory, *, job_id: str, client_slug: str,
        correlation_id: str | None,
    ) -> None:
        self._memory = memory
        self._job_id = job_id
        self._client_slug = client_slug
        self._correlation_id = correlation_id
        now = utcnow()
        self._doc = CampaignRunProgress(
            job_id=job_id,
            client_slug=client_slug,
            correlation_id=correlation_id,
            started_at=now,
            updated_at=now,
        )
        self._save()

    def _save(self) -> None:
        self._doc = self._doc.model_copy(update={"updated_at": utcnow()})
        self._memory.put(
            self._client_slug,
            CAMPAIGN_RUN_PROGRESS_KIND,
            self._job_id,
            self._doc.model_dump(mode="json"),
        )

    def stage_starting(self, stage: StageId) -> None:
        self._doc = self._doc.model_copy(
            update={"current_stage": stage, "last_stage_outcome": None}
        )
        self._save()

    def stage_finished(self, stage: StageId, outcome: StageOutcome) -> None:
        if outcome is StageOutcome.SUCCEEDED:
            self._doc = self._doc.model_copy(update={
                "stages_completed": [*self._doc.stages_completed, stage],
                "current_stage": None,
                "last_stage_outcome": "succeeded",
            })
        elif outcome is StageOutcome.FAILED:
            self._doc = self._doc.model_copy(update={
                "current_stage": None,
                "last_stage_outcome": "failed",
            })
        elif outcome is StageOutcome.BLOCKED:
            # A policy decision (the approval stage determined it blocks
            # publish), not a crash and not a plain success — deliberately
            # NOT added to stages_completed (see the module and field
            # docstrings for why) and NOT treated as an interruption
            # either, since current_stage is cleared here just like the
            # other two terminal cases.
            self._doc = self._doc.model_copy(update={
                "current_stage": None,
                "last_stage_outcome": "blocked",
            })
        else:  # SKIPPED is recorded via stages_skipped(), never reaches here
            raise ValueError(f"stage_finished() does not handle {outcome!r}")
        self._save()

    def stages_skipped(self, stages: list[StageId]) -> None:
        self._doc = self._doc.model_copy(
            update={"stages_skipped": [*self._doc.stages_skipped, *stages]}
        )
        self._save()


__all__ = [
    "CAMPAIGN_RUN_PROGRESS_KIND",
    "CAMPAIGN_RUN_PROGRESS_VERSION",
    "CampaignProgressTracker",
    "CampaignRunProgress",
]
