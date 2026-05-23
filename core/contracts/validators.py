"""Pure validators for MKT operational contracts.

Every function here is a pure mapping from ``dict`` to either ``(ok, errors)``
or a raise. No I/O, no filesystem, no network, no shared state.

Two flavors per contract:
- ``validate_X(payload)`` -> ``(bool, list[ContractErrorPayload])``
- ``validate_X_strict(payload)`` -> instance of the model, or raises ``ContractError``

The strict variants are convenient at workflow boundaries; the non-strict
variants are convenient for batch validation / reporting.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from .audit_trail import AuditTrailEvent
from .claim_audit import ClaimAudit
from .envelope import ReturnEnvelope
from .errors import ContractError, ContractErrorCode, ContractErrorPayload
from .phase_gate import PhaseGate, PhaseGateResult, PhaseTransition
from .workflow_run import WorkflowRunSummary

# Map pydantic error types to ContractErrorCode. Falls back to UNKNOWN.
_PYDANTIC_TYPE_TO_CODE: dict[str, ContractErrorCode] = {
    "missing": ContractErrorCode.MISSING_FIELD,
    "extra_forbidden": ContractErrorCode.EXTRA_FIELD,
    "value_error": ContractErrorCode.INVARIANT_VIOLATION,
    "string_pattern_mismatch": ContractErrorCode.SCHEMA_ERROR,
    "string_too_short": ContractErrorCode.SCHEMA_ERROR,
    "string_too_long": ContractErrorCode.SCHEMA_ERROR,
    "greater_than_equal": ContractErrorCode.SCHEMA_ERROR,
    "less_than_equal": ContractErrorCode.SCHEMA_ERROR,
    "literal_error": ContractErrorCode.VERSION_MISMATCH,
    "enum": ContractErrorCode.INVALID_ENUM,
    "datetime_type": ContractErrorCode.INVALID_TYPE,
    "datetime_from_date_parsing": ContractErrorCode.INVALID_TYPE,
}


def _path_from_loc(loc: tuple[Any, ...]) -> str:
    return "/" + "/".join(str(x) for x in loc) if loc else ""


def _classify(err_type: str, message: str) -> ContractErrorCode:
    # Inspect message FIRST — model_validators emit ``value_error`` regardless
    # of the semantic problem, so message substrings are the only way to
    # distinguish hash mismatch from duplicate ref from naive datetime.
    msg_lower = message.lower()
    if "hash mismatch" in msg_lower:
        return ContractErrorCode.HASH_MISMATCH
    if "timezone-aware" in msg_lower or "naive" in msg_lower:
        return ContractErrorCode.NAIVE_DATETIME
    if "duplicate" in msg_lower:
        return ContractErrorCode.DUPLICATE_REF
    if err_type in _PYDANTIC_TYPE_TO_CODE:
        return _PYDANTIC_TYPE_TO_CODE[err_type]
    return ContractErrorCode.UNKNOWN


def _from_pydantic(err: ValidationError, contract: str) -> list[ContractErrorPayload]:
    out: list[ContractErrorPayload] = []
    for raw in err.errors():
        msg = str(raw.get("msg", ""))
        code = _classify(str(raw.get("type", "")), msg)
        out.append(
            ContractErrorPayload(
                code=code,
                contract=contract,
                path=_path_from_loc(raw.get("loc", ())),
                message=msg or "validation failed",
                details={"pydantic_type": str(raw.get("type", ""))},
            )
        )
    return out


def _validate(model_cls: type[BaseModel], payload: dict[str, Any], contract: str):
    """Internal shared validation routine."""
    try:
        instance = model_cls.model_validate(payload)
        return True, [], instance
    except ValidationError as e:
        return False, _from_pydantic(e, contract), None


# ---------- Envelope ----------

def validate_envelope(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(ReturnEnvelope, payload, "envelope.v1")
    return ok, errs


def validate_envelope_strict(payload: dict[str, Any]) -> ReturnEnvelope:
    ok, errs, instance = _validate(ReturnEnvelope, payload, "envelope.v1")
    if not ok or instance is None:
        raise ContractError(errs[0])
    return instance


# ---------- ClaimAudit ----------

def validate_claim_audit(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(ClaimAudit, payload, "claim-audit.v1")
    return ok, errs


def validate_claim_audit_strict(payload: dict[str, Any]) -> ClaimAudit:
    ok, errs, instance = _validate(ClaimAudit, payload, "claim-audit.v1")
    if not ok or instance is None:
        raise ContractError(errs[0])
    return instance


# ---------- PhaseGate / Result / Transition ----------

def validate_phase_gate(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(PhaseGate, payload, "phase-gate.v1")
    return ok, errs


def validate_phase_gate_result(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(PhaseGateResult, payload, "phase-gate.v1")
    return ok, errs


def validate_phase_transition(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(PhaseTransition, payload, "phase-gate.v1")
    return ok, errs


def validate_phase_transition_strict(payload: dict[str, Any]) -> PhaseTransition:
    ok, errs, instance = _validate(PhaseTransition, payload, "phase-gate.v1")
    if not ok or instance is None:
        raise ContractError(errs[0])
    return instance


# ---------- AuditTrailEvent ----------

def validate_audit_event(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(AuditTrailEvent, payload, "audit-trail.v1")
    return ok, errs


def validate_audit_event_strict(payload: dict[str, Any]) -> AuditTrailEvent:
    ok, errs, instance = _validate(AuditTrailEvent, payload, "audit-trail.v1")
    if not ok or instance is None:
        raise ContractError(errs[0])
    return instance


# ---------- WorkflowRunSummary ----------

def validate_workflow_run(payload: dict[str, Any]) -> tuple[bool, list[ContractErrorPayload]]:
    ok, errs, _ = _validate(WorkflowRunSummary, payload, "workflow-run.v1")
    return ok, errs


def validate_workflow_run_strict(payload: dict[str, Any]) -> WorkflowRunSummary:
    ok, errs, instance = _validate(WorkflowRunSummary, payload, "workflow-run.v1")
    if not ok or instance is None:
        raise ContractError(errs[0])
    return instance
