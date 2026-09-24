"""Intake application service (architecture/application-service-boundary).

Migrates ``mkt intake`` onto the application layer. Behaviour-identical to
the CLI's inline implementation: same persisted entities, same audit
event shape, same three output files (``intake.json``,
``intake-summary.md``, ``brief.json``), same ``--strict`` semantics.

**Tenant-resolution split (Phase 6 — LOCAL CLI INPUT vs SAFE SERVICE
INPUT).** Every other application service in this package takes an
:class:`OperationContext` that already carries ``client_slug`` — the
context is built *before* the service is called. Intake cannot follow
that shape: the client slug does not exist yet: it is *derived* from the
intake document itself (``client_slug_override``, or a slugified company
name — see :meth:`core.intake.validator.IntakeValidator.validate`).

So this module exposes two entry points instead of one:

- :func:`parse_and_validate` — takes the raw, already-read JSON dict (the
  SAFE SERVICE INPUT: exactly what a future HTTP POST body would carry).
  Parses it into a :class:`ClientIntake`, runs
  :class:`~core.intake.validator.IntakeValidator`, and returns the
  resolved ``client_slug`` alongside both objects. Raises
  :class:`IntakeParseError` (never a raw Pydantic
  :class:`~pydantic.ValidationError`) when ``raw_intake`` doesn't parse —
  a caller catches that one controlled exception type to build its
  ``OperationResult``/HTTP error / etc.
- :func:`submit_intake` — takes an already-built :class:`OperationContext`
  (constructed by the caller using the slug :func:`parse_and_validate`
  just resolved) plus the already-validated ``intake``/``validation``
  pair, and does everything content-independent: persist, audit,
  normalize, write outputs.

Reading the intake file *off local disk by path* remains the CLI's job
(that's the LOCAL CLI INPUT — a future API adapter would instead read an
uploaded request body into the same raw ``dict`` and never see a
filesystem path at all). Everything from "I have a parsed JSON object"
onward is shared, tenant-safe application logic.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.intake import (
    INTAKE_KIND,
    SINGLETON_ID,
    VALIDATION_KIND,
    ClientIntake,
    IntakeNormalizationError,
    IntakeValidationResult,
    IntakeValidator,
    normalize_intake,
    render_intake_summary,
)
from core.memory import JsonFileMemory

from ..artifacts import OutputLayout, write_artifacts
from ..context import OperationContext
from ..result import ErrorCode, OperationResult

_ACTOR = "intake_service"


class IntakeParseError(Exception):
    """Raised by :func:`parse_and_validate` when ``raw_intake`` fails
    Pydantic validation against :class:`ClientIntake`. Carries the
    original :class:`~pydantic.ValidationError` as ``__cause__``."""


def parse_and_validate(
    raw_intake: dict[str, Any],
) -> tuple[ClientIntake, IntakeValidationResult]:
    """Parse + validate a raw intake dict, resolving its ``client_slug``.

    This is the ONLY step in the intake flow that runs before a
    ``client_slug`` — and therefore an :class:`OperationContext` — can
    exist. Callers (CLI today, an API adapter later) call this first,
    build their context with ``validation.client_slug``, then call
    :func:`submit_intake`.

    Raises:
        IntakeParseError: ``raw_intake`` is not a valid ``ClientIntake``.
    """
    try:
        intake = ClientIntake.model_validate(raw_intake)
    except ValidationError as e:
        raise IntakeParseError(str(e)) from e
    validation = IntakeValidator().validate(intake)
    return intake, validation


def submit_intake(
    ctx: OperationContext,
    *,
    intake: ClientIntake,
    validation: IntakeValidationResult,
    strict: bool = False,
) -> OperationResult:
    """Persist the validated intake, audit it, normalize a brief when
    possible, and write the three output files.

    ``ctx.client_slug`` MUST equal ``validation.client_slug`` — this is
    asserted, not silently corrected, because a mismatch would mean the
    caller built its context from the wrong resolved slug.
    """
    if ctx.client_slug != validation.client_slug:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=(
                f"OperationContext.client_slug={ctx.client_slug!r} does not "
                f"match the slug resolved from the intake document "
                f"({validation.client_slug!r})"
            ),
        )

    memory = JsonFileMemory(ctx.root)
    memory.put(ctx.client_slug, INTAKE_KIND, SINGLETON_ID, intake.model_dump(mode="json"))
    memory.put(
        ctx.client_slug, VALIDATION_KIND, SINGLETON_ID, validation.model_dump(mode="json"),
    )

    event = memory.append_audit_event_atomic(
        ctx.client_slug,
        lambda prev_hash_arg: AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor=_ACTOR,
            occurred_at=utcnow(),
            client_slug=ctx.client_slug,
            payload={
                "intake": {
                    "intake_id": validation.intake_id,
                    "client_slug": ctx.client_slug,
                    "is_valid": validation.is_valid,
                    "missing_critical": validation.missing_critical_count,
                    "missing_warning": validation.missing_warning_count,
                    "missing_info": validation.missing_info_count,
                    "action": "created",
                }
            },
            prev_hash=prev_hash_arg,
        ),
    )

    files = {
        "intake.json": intake.to_json(indent=2),
        "intake-summary.md": render_intake_summary(intake, validation),
    }
    if validation.can_normalize:
        try:
            brief = normalize_intake(intake, validation)
        except IntakeNormalizationError as e:
            return OperationResult.error_result(
                code=ErrorCode.INVALID_INPUT,
                message=f"normalization failed: {e}",
            )
        files["brief.json"] = brief.to_json(indent=2)

    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.PER_CLIENT,
        files=files,
        overwrite=True,  # intake has always overwritten its own outputs unconditionally
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code, message=write_err.message, remediation=write_err.remediation,
        )

    if strict and validation.missing_critical_count > 0:
        # Everything above already happened for real: intake/validation
        # are persisted, the audit event is written, and the artifact
        # files exist on disk (matches the CLI's long-standing behaviour
        # — "still write the summary + intake so the reviewer can fix"
        # even when --strict rejects the run). POLICY_BLOCKED must report
        # those real side effects, not hide them — see ErrorCode's
        # docstring and OperationResult.error_result's parameters.
        return OperationResult.error_result(
            code=ErrorCode.POLICY_BLOCKED,
            message=(
                f"--strict and critical issues present "
                f"({validation.missing_critical_count})"
            ),
            data={"intake": intake, "validation": validation},
            artifacts=artifacts,
            audit_event_id=event.event_id,
        )

    return OperationResult.ok_result(
        data={"intake": intake, "validation": validation},
        artifacts=artifacts,
        audit_event_id=event.event_id,
    )


__all__ = ["IntakeParseError", "parse_and_validate", "submit_intake"]
