"""Demo operations (MKT-11C) — deterministic, no external effect.

Exist solely to exercise the job lifecycle end to end: a normal success
path (``demo.echo``), a structured failure path (``demo.fail``), and the
WAITING_APPROVAL path (``demo.needs_approval``). All three are
``dev_only=True`` in their :class:`~core.jobs.registry.OperationSpec` — a
real deployment must never treat them as production capability.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.application.context import OperationContext
from core.application.result import ErrorCode

from ..models import JobOutcome
from ..registry import JobRegistry, JobRiskClass, OperationSpec


class EchoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=500)


def _echo_handler(ctx: OperationContext, params: EchoParams) -> JobOutcome:
    return JobOutcome.completed(data={"echo": params.message, "client_slug": ctx.client_slug})


class FailParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


def _fail_handler(ctx: OperationContext, params: FailParams) -> JobOutcome:
    return JobOutcome.failed(code=ErrorCode.INVALID_INPUT, message=params.reason)


class NeedsApprovalParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


def _needs_approval_handler(ctx: OperationContext, params: NeedsApprovalParams) -> JobOutcome:
    return JobOutcome.waiting_approval(reason=params.reason)


def register_demo_operations(registry: JobRegistry) -> None:
    """Register all three demo operations on ``registry``. Called on
    :data:`~core.jobs.registry.default_registry` at package import time,
    and by every test that wants an isolated registry with the same
    fixtures."""
    registry.register(OperationSpec(
        operation="demo.echo",
        params_model=EchoParams,
        handler=_echo_handler,
        risk_class=JobRiskClass.LOW,
        description="Echo a message back — proves the QUEUED->RUNNING->COMPLETED path.",
        dev_only=True,
    ))
    registry.register(OperationSpec(
        operation="demo.fail",
        params_model=FailParams,
        handler=_fail_handler,
        risk_class=JobRiskClass.LOW,
        description="Always fails with the supplied reason — proves the FAILED path.",
        dev_only=True,
    ))
    registry.register(OperationSpec(
        operation="demo.needs_approval",
        params_model=NeedsApprovalParams,
        handler=_needs_approval_handler,
        risk_class=JobRiskClass.LOW,
        description="Always pauses for approval — proves the WAITING_APPROVAL path.",
        dev_only=True,
    ))


__all__ = [
    "EchoParams",
    "FailParams",
    "NeedsApprovalParams",
    "register_demo_operations",
]
