"""``campaign.run`` job operation (MKT-11D).

Wraps :func:`core.application.services.campaign_run.run_campaign` — the
handler contains no pipeline logic of its own, only the translation from
:class:`~core.application.services.campaign_run.CampaignRunOutcome` to
:class:`~core.jobs.models.JobOutcome`.

**Job-lifecycle semantics are conceptually separate from the legacy CLI's
exit codes** (MKT-11D approved design): ``blocks_publish=False`` always
means ``COMPLETED``; ``blocks_publish=True`` always means
``WAITING_APPROVAL`` — regardless of whether the underlying pipeline
reached that state via ``--require-approval`` (an exception, in the legacy
path), ``--stop-on-blocked``, or the default (both a quiet return, in the
legacy path). The legacy CLI (``cli/main.py::_cmd_run_campaign``) is the
only place that still branches on those flags to pick 0 vs 3.

``cancel_support=False`` — a partial mid-pipeline stop would leave
inconsistent state (some stages persisted, some not); this operation must
run to one of its three terminal-ish outcomes once started, exactly like
every other job today (MKT-11C's synchronous-runner limitation).
"""

from __future__ import annotations

from core.application.context import OperationContext
from core.application.result import ErrorCode
from core.application.services.campaign_run import (
    CampaignRunOutcomeKind,
    CampaignRunParams,
    run_campaign,
)
from core.memory import JsonFileMemory

from ..models import JobOutcome
from ..registry import JobRegistry, JobRiskClass, OperationSpec


def _campaign_run_handler(
    ctx: OperationContext, params: CampaignRunParams,
) -> JobOutcome:
    memory = JsonFileMemory(ctx.root)
    outcome = run_campaign(
        memory=memory,
        outputs_root=ctx.outputs_root,
        params=params,
        job_id=ctx.job_id,  # populated by InlineJobRunner._context_for
        correlation_id=ctx.correlation_id,
    )

    if outcome.kind is CampaignRunOutcomeKind.COMPLETED:
        return JobOutcome.completed(
            data=outcome.summary_data,
            result_ref=(
                f"{ctx.client_slug}/campaign_run_summary/current"
                if outcome.summary_data else None
            ),
        )
    if outcome.kind is CampaignRunOutcomeKind.BLOCKED:
        assert outcome.summary_data is not None
        approval_pack_id = outcome.summary_data.get("approval_pack_id")
        return JobOutcome.waiting_approval(
            reason=(
                "Approval Pack blocks publish — creative/visual stages "
                "were skipped. Review and approve/reject via `mkt "
                "approvals show` / `mkt approve` / `mkt reject`, then "
                "resubmit a new campaign.run job (no automatic resume in "
                "MKT-11D; see docs/MKT-11D-Campaign-Job-Migration-Inventory.md)."
            ),
            data=outcome.summary_data,
            result_ref=(
                f"{ctx.client_slug}/approval_pack/{approval_pack_id}"
                if approval_pack_id else None
            ),
        )
    # STRICT_FAILURE
    assert outcome.message is not None
    return JobOutcome.failed(code=ErrorCode.INVALID_INPUT, message=outcome.message)


def register_campaign_operations(registry: JobRegistry) -> None:
    """Register ``campaign.run`` on ``registry``. Called on
    :data:`~core.jobs.registry.default_registry` at package import time,
    and by every test that wants an isolated registry with this
    operation."""
    registry.register(OperationSpec(
        operation="campaign.run",
        params_model=CampaignRunParams,
        handler=_campaign_run_handler,
        risk_class=JobRiskClass.HIGH,
        description=(
            "Run the full campaign pipeline (intake -> strategy -> "
            "approval -> creative -> visual -> summary) as a job. "
            "Equivalent to `mkt run-campaign`, executed through the job "
            "system instead of blocking the calling process."
        ),
        cancel_support=False,
        long_running=True,
        produces_artifacts=True,
        may_wait_for_approval=True,
    ))


__all__ = ["register_campaign_operations"]
