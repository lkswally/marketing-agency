"""Pydantic models for the Campaign Pipeline Orchestrator (MKT-3F).

Contract: ``pipeline-run.v1``.

The summary is the meta-artifact a single ``mkt run-campaign`` run
produces. It references every pack persisted by the underlying layers
(intake → strategy → approval → creative → visual) but does NOT
duplicate their content.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.creative.models import CreativeAssetState
from core.domain.base import DomainModel, new_id, validate_slug
from core.strategy.backends.invocation_log import ClaudeInvocationRecord

PIPELINE_RUN_VERSION = "pipeline-run.v1"


# ============ Enums ============

class StageId(StrEnum):
    """The six stages the orchestrator walks through."""

    INTAKE = "intake"
    STRATEGY = "strategy"
    APPROVAL = "approval"
    CREATIVE = "creative"
    VISUAL = "visual"
    SUMMARY = "summary"


class StageOutcome(StrEnum):
    """Per-stage outcome surfaced in the summary."""

    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    FAILED = "failed"


# ============ Sub-models ============

class StageResult(DomainModel):
    """Outcome of one stage in a campaign pipeline run."""

    stage_id: StageId
    outcome: StageOutcome
    started_at: datetime
    finished_at: datetime
    artifact_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("stage timestamps must be timezone-aware (UTC)")
        return v


# ============ Top-level ============

class CampaignRunSummary(DomainModel):
    """End-of-run record for one ``mkt run-campaign`` invocation."""

    contract_version: Literal["pipeline-run.v1"] = PIPELINE_RUN_VERSION
    run_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    started_at: datetime
    finished_at: datetime

    # Provenance references (None when the stage was skipped or did not run).
    intake_id: str | None = None
    validation_id: str | None = None
    brief_path: str | None = None
    report_id: str | None = None
    approval_pack_id: str | None = None
    creative_pack_id: str | None = None
    visual_pack_id: str | None = None

    # Aggregate state
    overall_state: CreativeAssetState
    blocks_publish: bool = False
    intake_critical_count: int = Field(default=0, ge=0)
    intake_warning_count: int = Field(default=0, ge=0)
    intake_info_count: int = Field(default=0, ge=0)

    # Per-stage results (always six entries, ordered)
    stages: list[StageResult] = Field(default_factory=list)

    # Metadata
    rule_set_id: str | None = None

    # Strategy backend bookkeeping (MKT-4A)
    backend_requested: Literal["templated", "claude"] = "templated"
    """The backend the operator asked for via ``--backend`` (or default)."""

    backend_effective: Literal["templated", "claude", "mixed"] = "templated"
    """What actually produced the content:
    - ``"templated"``: every creative call came from the templated backend.
    - ``"claude"``: every creative call came from Claude with no fallback.
    - ``"mixed"``: some calls came from Claude, some fell back to templated.
    """

    backend_fallback_count: int = Field(default=0, ge=0)
    """Number of creative methods that fell back. Always 0 for
    ``backend_requested="templated"``. May be 1..6 for ``"claude"``."""

    backend_fallback_notes: list[str] = Field(default_factory=list)
    """One short note per fallback. Format: ``"<method>: <reason>"``.
    Surfaced in ``campaign-final-summary.md`` and on stderr by the CLI."""

    claude_invocations: list[ClaudeInvocationRecord] = Field(default_factory=list)
    """One record per real Claude call attempt (MKT-4B). Empty when
    using the templated backend; populated by
    :class:`AnthropicSDKInvoker`. Each record carries model id,
    request id, token counts, duration and an ``ok`` flag — never
    the prompt body, the model output, or the API key."""

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    # -------- helpers --------

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def count_by_outcome(self) -> dict[str, int]:
        counts = {o.value: 0 for o in StageOutcome}
        for s in self.stages:
            counts[s.outcome.value] += 1
        return counts

    def get_stage(self, stage_id: StageId) -> StageResult | None:
        for s in self.stages:
            if s.stage_id is stage_id:
                return s
        return None

    @property
    def is_complete(self) -> bool:
        """True iff every stage either succeeded or was skipped (no FAILED / BLOCKED)."""
        bad = {StageOutcome.FAILED, StageOutcome.BLOCKED}
        return not any(s.outcome in bad for s in self.stages)
