"""Contract tests for PhaseGate / PhaseGateResult / PhaseTransition (phase-gate.v1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.contracts import (
    ContractError,
    ContractErrorCode,
    GateSeverity,
    PhaseGate,
    PhaseGateResult,
    PhaseTransition,
    PredicateKind,
    validate_phase_gate,
    validate_phase_gate_result,
    validate_phase_transition,
    validate_phase_transition_strict,
)

pytestmark = pytest.mark.contract


def _now() -> datetime:
    return datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


# ---------- PhaseGate ----------

def test_gate_serialization_round_trip() -> None:
    g = PhaseGate(
        id="g1",
        name="Envelope present",
        phase="fase_3",
        predicate_kind=PredicateKind.ENVELOPE_PRESENT,
        params={"agent": "copywriter"},
        severity=GateSeverity.BLOCKING,
        description="Require envelope before transition.",
    )
    reloaded = PhaseGate.from_json(g.to_json())
    assert reloaded.model_dump() == g.model_dump()


def test_gate_rejects_unknown_predicate_kind() -> None:
    ok, errs = validate_phase_gate(
        {
            "id": "g1",
            "name": "x",
            "phase": "p",
            "predicate_kind": "vibes",
        }
    )
    assert ok is False
    assert any(e.code is ContractErrorCode.INVALID_ENUM for e in errs)


# ---------- PhaseGateResult ----------

def test_failed_result_requires_blocker() -> None:
    with pytest.raises(ValidationError):
        PhaseGateResult(gate_id="g1", passed=False, evaluated_at=_now())


def test_failed_result_with_blocker_is_ok() -> None:
    r = PhaseGateResult(
        gate_id="g1", passed=False, evaluated_at=_now(), blockers=["envelope missing"]
    )
    assert r.passed is False


def test_naive_evaluated_at_rejected() -> None:
    ok, errs = validate_phase_gate_result(
        {"gate_id": "g1", "passed": True, "evaluated_at": "2026-05-22T12:00:00"}
    )
    assert ok is False
    assert any(e.code is ContractErrorCode.NAIVE_DATETIME for e in errs)


def test_passed_result_serializes() -> None:
    r = PhaseGateResult(gate_id="g1", passed=True, evaluated_at=_now())
    payload = json.loads(r.to_json())
    assert payload["passed"] is True
    assert payload["contract_version"] == "phase-gate.v1"


# ---------- PhaseTransition ----------

def test_transition_passed_aggregates_all_results() -> None:
    t = PhaseTransition(
        from_phase="fase_2",
        to_phase="fase_3",
        gate_results=[
            PhaseGateResult(gate_id="g1", passed=True, evaluated_at=_now()),
            PhaseGateResult(gate_id="g2", passed=True, evaluated_at=_now()),
        ],
    )
    assert t.passed is True


def test_transition_fails_if_any_result_failed() -> None:
    t = PhaseTransition(
        from_phase="fase_2",
        to_phase="fase_3",
        gate_results=[
            PhaseGateResult(gate_id="g1", passed=True, evaluated_at=_now()),
            PhaseGateResult(
                gate_id="g2", passed=False, evaluated_at=_now(), blockers=["x"]
            ),
        ],
    )
    assert t.passed is False


def test_transition_rejects_duplicate_gate_ids() -> None:
    payload = {
        "from_phase": "a",
        "to_phase": "b",
        "gate_results": [
            {"gate_id": "g1", "passed": True, "evaluated_at": _now().isoformat()},
            {"gate_id": "g1", "passed": True, "evaluated_at": _now().isoformat()},
        ],
    }
    ok, errs = validate_phase_transition(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.DUPLICATE_REF for e in errs)


def test_strict_transition_raises() -> None:
    payload = {"from_phase": "a", "to_phase": "b", "gate_results": "not-a-list"}
    with pytest.raises(ContractError):
        validate_phase_transition_strict(payload)
