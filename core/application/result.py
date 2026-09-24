"""Structured operation result (MKT-11A).

Every application service returns an :class:`OperationResult` — it never
raises a domain exception to its caller. Adapters (CLI today; API/UI
later) translate ``status`` into their own transport (exit code, HTTP
status, toast) without needing to know which domain exception fired.

Internal domain exceptions (``EntityNotFound``, ``ApprovalStateError``,
``ImporterError``, ...) are caught *inside* each service function and
mapped to an :class:`OperationError` with a stable :class:`ErrorCode`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from core.domain.base import new_id


class OperationStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class ErrorCode(StrEnum):
    """Stable vocabulary an adapter can switch on without string-matching
    an exception message. Extend as new services are added — never repurpose
    an existing value."""

    NOT_FOUND = "not_found"
    """The referenced entity does not exist (e.g. no snapshot, no pack)."""

    INVALID_INPUT = "invalid_input"
    """Malformed argument — bad date, bad JSON, failed model validation."""

    UNKNOWN_OPERATION = "unknown_operation"
    """A job named an operation the registry has no spec for (MKT-11C).
    Kept distinct from INVALID_INPUT — a bad param value and a bad
    operation name are different classes of caller mistake, even though
    both currently map to the same exit code (2)."""

    INVALID_STATE_TRANSITION = "invalid_state_transition"
    """Domain state machine refused the transition (e.g. re-reject an
    already-APPROVED pack)."""

    ALREADY_EXISTS = "already_exists"
    """Output already present and overwrite was not requested."""

    PATH_NOT_ALLOWED = "path_not_allowed"
    """Resolved artifact path escapes the permitted output root."""

    PERMISSION_DENIED = "permission_denied"
    """The actor's role does not authorize this operation (MKT-11B)."""

    POLICY_BLOCKED = "policy_blocked"
    """A caller-requested policy prevented the operation from being
    considered successful, independently of authorization or malformed
    input (architecture/application-service-boundary) — e.g.
    ``--strict`` + critical intake issues, or ``--require-approval`` + a
    blocks-publish Approval Pack. Distinct from PERMISSION_DENIED
    (actor/role authorization) and INVALID_INPUT (malformed data): the
    input was well-formed and the actor was allowed to call the
    operation, but the caller opted into a stricter outcome than the
    underlying domain state satisfies.

    Deliberately neutral about WHEN the block happens relative to any
    side effects: some callers gate BEFORE doing domain work (e.g.
    ``build_creative_pack``'s ``--require-approval`` check runs before
    the factory builds anything — no side effects occur), others gate
    AFTER legitimate side effects already landed (e.g.
    ``submit_intake``'s ``--strict`` check runs after persisting the
    intake/validation, writing artifacts, and appending the audit event
    — those effects are real and must be reported, not hidden). See
    :meth:`OperationResult.error_result`'s ``data``/``artifacts``/
    ``audit_event_id`` parameters for how a caller reports which case
    applies."""

    PERSISTENCE_ERROR = "persistence_error"
    """The stored entity could not be read back — corrupted JSON or a
    schema mismatch (MKT-11B). Distinct from NOT_FOUND: the record exists
    on disk but cannot be deserialised."""

    INTERNAL = "internal"
    """Unexpected failure — caught, never a raw traceback to the caller."""


class OperationError(BaseModel):
    """Structured error — the only way a failure reaches the caller."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    remediation: str | None = None
    """Human-actionable next step, e.g. "run `mkt import-metrics` first"."""


class Artifact(BaseModel):
    """One file the operation produced (or would produce, in dry-run)."""

    model_config = ConfigDict(frozen=True)

    path: Path
    kind: str
    """Free-form discriminator, e.g. ``"markdown"`` / ``"json"``."""
    would_write: bool = False
    """True in dry-run: the path is where the file WOULD land, and it was
    not actually written."""


class OperationWarning(BaseModel):
    """A non-fatal notice — the operation still succeeded."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class OperationResult(BaseModel):
    """Structured outcome of one application-service call."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    operation_id: str = Field(default_factory=new_id)
    status: OperationStatus
    data: Any = None
    """The service's primary payload — a Pydantic model, dict, or list,
    depending on the service. Adapters know the shape per call site."""
    artifacts: list[Artifact] = Field(default_factory=list)
    warnings: list[OperationWarning] = Field(default_factory=list)
    error: OperationError | None = None
    audit_event_id: str | None = None
    """Populated when the operation appended an audit event. ``None``
    for pure reads."""

    @property
    def ok(self) -> bool:
        return self.status is OperationStatus.OK

    @classmethod
    def ok_result(
        cls,
        *,
        data: Any = None,
        artifacts: list[Artifact] | None = None,
        warnings: list[OperationWarning] | None = None,
        audit_event_id: str | None = None,
    ) -> OperationResult:
        return cls(
            status=OperationStatus.OK,
            data=data,
            artifacts=artifacts or [],
            warnings=warnings or [],
            audit_event_id=audit_event_id,
        )

    @classmethod
    def error_result(
        cls,
        *,
        code: ErrorCode,
        message: str,
        remediation: str | None = None,
        data: Any = None,
        artifacts: list[Artifact] | None = None,
        warnings: list[OperationWarning] | None = None,
        audit_event_id: str | None = None,
    ) -> OperationResult:
        """Build an ERROR result.

        ``data``/``artifacts``/``warnings``/``audit_event_id`` are
        optional and default to empty/``None`` — the overwhelming
        majority of errors (bad input, not found, permission denied)
        have no side effects to report. They exist for the narrower case
        where a caller (most notably a POLICY_BLOCKED one — see that
        code's docstring) already performed real, persisted side effects
        BEFORE deciding the overall operation counts as a failure: the
        caller passes exactly what actually happened, never fabricated.
        A caller whose policy gate runs before any domain work simply
        omits these and gets the same empty/``None`` result as before
        this parameter existed.
        """
        return cls(
            status=OperationStatus.ERROR,
            error=OperationError(code=code, message=message, remediation=remediation),
            data=data,
            artifacts=artifacts or [],
            warnings=warnings or [],
            audit_event_id=audit_event_id,
        )


__all__ = [
    "Artifact",
    "ErrorCode",
    "OperationError",
    "OperationResult",
    "OperationStatus",
    "OperationWarning",
]
