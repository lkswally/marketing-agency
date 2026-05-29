"""Predicate evaluator tests — envelope_present, status_equals, evaluate_required_gate."""

from __future__ import annotations

import pytest

from core.runtime import (
    RunState,
    UnknownPredicate,
    evaluable_kinds,
    evaluate,
    evaluate_required_gate,
)


def _state(envelopes=None, held_gates=None) -> RunState:
    return RunState(
        run_id="r1",
        workflow_id="W1_intake_to_strategy",
        client_slug="default",
        envelopes=list(envelopes or []),
        held_gates=set(held_gates or set()),
    )


# ---------- evaluate_required_gate (the dispatcher's choke point) ----------

def test_required_gate_held_returns_passed() -> None:
    state = _state(held_gates={"g_brief_captured"})
    ok, blockers = evaluate_required_gate(state, "g_brief_captured")
    assert ok is True
    assert blockers == []


def test_required_gate_missing_returns_blockers() -> None:
    state = _state(held_gates=set())
    ok, blockers = evaluate_required_gate(state, "g_brief_captured")
    assert ok is False
    assert blockers and "g_brief_captured" in blockers[0]


# ---------- envelope_present ----------

def test_envelope_present_finds_match() -> None:
    state = _state(envelopes=[{"agent": "copywriter", "status": "completado"}])
    ok, blockers = evaluate("envelope_present", state, {"agent": "copywriter"})
    assert ok is True
    assert blockers == []


def test_envelope_present_no_match() -> None:
    state = _state(envelopes=[{"agent": "strategist", "status": "completado"}])
    ok, blockers = evaluate("envelope_present", state, {"agent": "copywriter"})
    assert ok is False
    assert blockers and "copywriter" in blockers[0]


def test_envelope_present_missing_param() -> None:
    state = _state()
    ok, blockers = evaluate("envelope_present", state, {})
    assert ok is False
    assert "agent" in blockers[0]


# ---------- status_equals ----------

def test_status_equals_matches() -> None:
    state = _state(envelopes=[{"agent": "qa", "status": "PASS"}])
    ok, blockers = evaluate(
        "status_equals", state, {"agent": "qa", "expected_status": "PASS"}
    )
    assert ok is True
    assert blockers == []


def test_status_equals_mismatch() -> None:
    state = _state(envelopes=[{"agent": "qa", "status": "FAIL"}])
    ok, blockers = evaluate(
        "status_equals", state, {"agent": "qa", "expected_status": "PASS"}
    )
    assert ok is False
    assert "PASS" in blockers[0] and "FAIL" in blockers[0]


def test_status_equals_uses_latest_envelope() -> None:
    state = _state(
        envelopes=[
            {"agent": "qa", "status": "FAIL"},
            {"agent": "qa", "status": "PASS"},
        ]
    )
    ok, _ = evaluate(
        "status_equals", state, {"agent": "qa", "expected_status": "PASS"}
    )
    assert ok is True


def test_status_equals_no_envelope_for_agent() -> None:
    state = _state()
    ok, blockers = evaluate(
        "status_equals", state, {"agent": "qa", "expected_status": "PASS"}
    )
    assert ok is False
    assert "no envelope" in blockers[0]


def test_status_equals_missing_params() -> None:
    state = _state()
    ok, blockers = evaluate("status_equals", state, {})
    assert ok is False
    assert "expected_status" in blockers[0]


# ---------- registry hygiene ----------

def test_evaluable_kinds_includes_both() -> None:
    kinds = evaluable_kinds()
    assert "envelope_present" in kinds
    assert "status_equals" in kinds


def test_unknown_kind_raises() -> None:
    state = _state()
    with pytest.raises(UnknownPredicate):
        evaluate("vibes_check", state, {})


def test_kind_known_but_not_registered_raises() -> None:
    # claims_audit_present is a real PredicateKind but no evaluator registered.
    state = _state()
    with pytest.raises(UnknownPredicate):
        evaluate("claims_audit_present", state, {})
