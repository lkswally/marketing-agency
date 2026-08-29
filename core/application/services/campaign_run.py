"""Campaign run application service (MKT-11D).

Single shared entry point for the full campaign pipeline
(``PipelineOrchestrator``), used by **both** the legacy ``mkt run-campaign``
CLI command and the ``campaign.run`` job operation
(:mod:`core.jobs.operations.campaign`). Neither caller duplicates the
orchestrator-invocation logic — they each translate the resulting
:class:`CampaignRunOutcome` into their own contract (legacy exit codes for
the CLI, :class:`~core.jobs.models.JobOutcome` for the job handler).

**MKT-11D adjustment 2 (execution-time validation):** :func:`run_campaign`
always re-validates ``intake_path`` for real — file exists, parses as JSON,
matches the ``ClientIntake`` schema — regardless of any earlier preflight a
caller may have done. Between a job's ``submit`` and its ``run`` the file
can disappear, change, or lose permissions; a job must never trust
submit-time state.

**MKT-11D adjustment 1 (verified, not assumed):** ``PipelineStrictFailure``
has exactly one raise site in ``core/pipeline/orchestrator.py``
(``_finalize_failure``), gated by
``strict and validation is not None and validation.missing_critical_count > 0``
— i.e. it can only ever represent an invalid/incomplete intake input, never
a stage-execution, contract, or output failure. Confirmed by reading every
reference to the exception class before writing this mapping.
``ErrorCode.INVALID_INPUT`` is therefore semantically correct, not a
placeholder chosen to avoid adding an enum value.

**Secret handling:** ``ANTHROPIC_API_KEY`` is read from ``os.environ``
inside :func:`resolve_strategy_backend`, at call time, and is never placed
into ``CampaignRunParams``, the returned :class:`CampaignRunOutcome`, or
any log/warning string. This mirrors the legacy CLI's existing behaviour
exactly — the code was moved here, not changed.
"""

from __future__ import annotations

import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.intake.models import ClientIntake
from core.intake.validator import IntakeValidator
from core.memory import Memory
from core.pipeline import (
    PIPELINE_RUN_KIND,
    PIPELINE_RUN_SINGLETON,
    CampaignRunSummary,
    PipelineBlockedByApproval,
    PipelineOrchestrator,
    PipelineStrictFailure,
)
from core.strategy import (
    AnthropicSDKInvoker,
    ClaudeStrategyBackend,
    NoCredentialsError,
    RefusingClaudeInvoker,
    StrategyBackend,
)


class CampaignRunParams(BaseModel):
    """Real, existing ``mkt run-campaign`` arguments only — no invented
    fields. See ``docs/MKT-11D-Campaign-Job-Migration-Inventory.md`` §1."""

    model_config = ConfigDict(extra="forbid")

    intake_path: Annotated[str, Field(min_length=1, max_length=4000)]
    strict: bool = False
    require_approval: bool = False
    stop_on_blocked: bool = False
    backend: Literal["templated", "claude"] = "templated"
    claude_model: str | None = None


class CampaignRunOutcomeKind(StrEnum):
    COMPLETED = "completed"
    """``blocks_publish=False`` — every stage ran, nothing pending."""

    BLOCKED = "blocked"
    """``blocks_publish=True`` — reached regardless of which of
    ``require_approval`` / ``stop_on_blocked`` / neither produced it
    (MKT-11D §3b of the inventory: all three are the same underlying
    pipeline event). Never treated as a failure."""

    STRICT_FAILURE = "strict_failure"
    """Invalid/incomplete input — missing intake file, malformed intake,
    or ``PipelineStrictFailure``. Always ``ErrorCode.INVALID_INPUT`` for
    callers that need one (see module docstring, adjustment 1)."""


class CampaignRunOutcome(BaseModel):
    """What :func:`run_campaign` returns — never raises the two pipeline
    exceptions to its own caller."""

    model_config = ConfigDict(frozen=True)

    kind: CampaignRunOutcomeKind
    summary_data: dict[str, Any] | None = None
    """Populated for COMPLETED and BLOCKED. ``None`` for STRICT_FAILURE."""
    message: str | None = None
    """Populated for STRICT_FAILURE — the human-readable reason."""
    warnings: list[str] = Field(default_factory=list)
    """Backend-fallback / no-credentials warnings — never an error, never
    routed anywhere by this function. The caller decides where they go
    (stderr for the legacy CLI; ``JobOutcome`` data for the job path)."""


def resolve_strategy_backend(
    backend: str, claude_model: str | None,
) -> tuple[StrategyBackend | None, str | None]:
    """Moved verbatim from ``cli/main.py::_cmd_run_campaign`` (MKT-11D) —
    not reimplemented. Returns ``(backend_or_none, warning_or_none)``.
    Reads ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_MODEL`` from the environment
    at call time; never returns or logs the key itself."""
    if backend != "claude":
        return None, None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = claude_model or os.environ.get("ANTHROPIC_MODEL")
    if not api_key:
        return (
            ClaudeStrategyBackend(invoker=RefusingClaudeInvoker()),
            "--backend claude requested but ANTHROPIC_API_KEY is not set. "
            "Wiring RefusingClaudeInvoker — every creative method will fall "
            "back to the templated backend. Set the env var to enable real "
            "Claude calls.",
        )
    try:
        invoker = AnthropicSDKInvoker(api_key=api_key, model=model)
        return ClaudeStrategyBackend(invoker=invoker), None
    except NoCredentialsError as e:
        return (
            ClaudeStrategyBackend(invoker=RefusingClaudeInvoker()),
            f"--backend claude requested but the SDK is not available: {e}. "
            "Falling back to templated.",
        )


def run_campaign(
    *,
    memory: Memory,
    outputs_root: Path,
    params: CampaignRunParams,
    job_id: str | None = None,
    correlation_id: str | None = None,
) -> CampaignRunOutcome:
    """Validate the intake for real, run the pipeline, and translate its
    outcome. Never raises ``PipelineStrictFailure`` /
    ``PipelineBlockedByApproval`` — both are caught here."""

    intake_path = Path(params.intake_path)
    if not intake_path.exists():
        return CampaignRunOutcome(
            kind=CampaignRunOutcomeKind.STRICT_FAILURE,
            message=f"intake file not found: {intake_path}",
        )

    # Adjustment 2 — real, execution-time validation. Mirrors exactly what
    # PipelineOrchestrator._stage_intake does internally; this pass exists
    # so a job whose intake went stale between submit and run fails with a
    # structured CampaignRunOutcome instead of an unhandled exception, and
    # so this function can recover `client_slug` for the BLOCKED path
    # below without inventing a second slug-derivation rule.
    try:
        raw = json.loads(intake_path.read_text(encoding="utf-8"))
        intake = ClientIntake.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, OSError) as e:
        return CampaignRunOutcome(
            kind=CampaignRunOutcomeKind.STRICT_FAILURE,
            message=f"invalid intake file: {e}",
        )
    validation = IntakeValidator().validate(intake)
    client_slug = validation.client_slug

    strategy_backend, backend_warning = resolve_strategy_backend(
        params.backend, params.claude_model,
    )
    warnings: list[str] = [backend_warning] if backend_warning else []

    orchestrator = PipelineOrchestrator(
        memory=memory,
        outputs_root=outputs_root,
        job_id=job_id,
        correlation_id=correlation_id,
    )
    try:
        summary = orchestrator.run_from_file(
            intake_path,
            strict=params.strict,
            require_approval=params.require_approval,
            stop_on_blocked=params.stop_on_blocked,
            strategy_backend=strategy_backend,
        )
    except PipelineStrictFailure as e:
        return CampaignRunOutcome(
            kind=CampaignRunOutcomeKind.STRICT_FAILURE,
            message=str(e),
            warnings=warnings,
        )
    except PipelineBlockedByApproval:
        # The orchestrator already persisted the summary right before
        # raising (orchestrator.py, require_approval + blocks_publish
        # branch) — reload it rather than reconstructing state.
        raw_summary = memory.get(client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON)
        summary = CampaignRunSummary.model_validate(raw_summary)

    if summary.backend_requested == "claude" and summary.backend_fallback_count > 0:
        warnings.append(
            f"--backend claude requested but {summary.backend_fallback_count} "
            f"of 6 creative method(s) fell back to templated. effective "
            f"backend = '{summary.backend_effective}'. No real Claude "
            "invoker is wired (MKT-4A ships infrastructure only; wire one "
            "in MKT-4B). See campaign-final-summary.md for details."
        )

    data = _summary_payload(summary, outputs_root)
    kind = (
        CampaignRunOutcomeKind.BLOCKED
        if summary.blocks_publish
        else CampaignRunOutcomeKind.COMPLETED
    )
    return CampaignRunOutcome(kind=kind, summary_data=data, warnings=warnings)


def _summary_payload(summary: CampaignRunSummary, outputs_root: Path) -> dict[str, Any]:
    """Same field set the legacy CLI has always printed to stdout — moved,
    not changed, so `_job_payload`-style callers and the legacy JSON
    payload stay in lockstep."""
    return {
        "run_id": summary.run_id,
        "client_slug": summary.client_slug,
        "contract_version": summary.contract_version,
        "overall_state": summary.overall_state.value,
        "blocks_publish": summary.blocks_publish,
        "is_complete": summary.is_complete,
        "duration_seconds": round(summary.duration_seconds, 3),
        "intake_critical": summary.intake_critical_count,
        "intake_warning": summary.intake_warning_count,
        "intake_info": summary.intake_info_count,
        "report_id": summary.report_id,
        "approval_pack_id": summary.approval_pack_id,
        "creative_pack_id": summary.creative_pack_id,
        "visual_pack_id": summary.visual_pack_id,
        "stage_counts": summary.count_by_outcome(),
        "outputs_dir": str(outputs_root / summary.client_slug),
        "backend_requested": summary.backend_requested,
        "backend_effective": summary.backend_effective,
        "backend_fallback_count": summary.backend_fallback_count,
        "backend_fallback_notes": list(summary.backend_fallback_notes),
    }


__all__ = [
    "CampaignRunOutcome",
    "CampaignRunOutcomeKind",
    "CampaignRunParams",
    "resolve_strategy_backend",
    "run_campaign",
]
