"""Operation context (MKT-11A).

Every application-service call takes an :class:`OperationContext`. It is
the *only* path to a client slug — no service accepts a bare string
alongside a context — which is what makes cross-tenant writes structurally
impossible rather than merely discouraged by convention.

The context also carries the actor/role/source/correlation fields D-11.6
asked for, ahead of any real auth system. No authorization decision is
made here or anywhere in this package — ``role`` is recorded for audit
and for a *future* policy layer to consult; it is not enforced by this
milestone.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.domain.base import new_id, utcnow, validate_slug

DEFAULT_DATA_ROOT = Path("data/clients")
DEFAULT_OUTPUTS_ROOT = Path("outputs")


class OperationRole(StrEnum):
    """Roles the domain is prepared to record. Not enforced here —
    D-11.6 explicitly defers authorization to a future policy layer."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


class OperationSource(StrEnum):
    """Which adapter initiated the call — recorded for audit/telemetry,
    never branched on for behaviour (that would defeat the point of a
    shared application layer)."""

    CLI = "cli"
    API = "api"
    UI = "ui"
    WORKER = "worker"


class OperationContext(BaseModel):
    """Immutable request-scoped context passed into every application
    service call."""

    model_config = ConfigDict(frozen=True)

    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    root: Path = DEFAULT_DATA_ROOT
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT

    actor_id: str = "unknown"
    role: OperationRole = OperationRole.OPERATOR
    source: OperationSource = OperationSource.CLI
    correlation_id: str = Field(default_factory=new_id)
    requested_at: datetime = Field(default_factory=utcnow)

    job_id: str | None = None
    """Set by :class:`~core.jobs.runner.InlineJobRunner` (MKT-11D) when a
    handler is invoked as part of job execution — ``None`` for every
    direct (non-job) service call, which is every call before MKT-11D and
    every call to a non-job service after it. A handler that wants to
    correlate its own work (e.g. pipeline audit events) with the owning
    job reads this field; nothing else in ``core.application`` branches
    on it."""

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)


__all__ = [
    "DEFAULT_DATA_ROOT",
    "DEFAULT_OUTPUTS_ROOT",
    "OperationContext",
    "OperationRole",
    "OperationSource",
]
