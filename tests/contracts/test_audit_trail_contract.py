"""Contract tests for AuditTrailEvent (audit-trail.v1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.contracts import (
    AuditEventType,
    AuditTrailEvent,
    ContractError,
    ContractErrorCode,
    compute_event_hash,
    validate_audit_event,
    validate_audit_event_strict,
    verify_chain,
)

pytestmark = pytest.mark.contract


def _now() -> datetime:
    return datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


# ---------- compute_event_hash ----------

def test_compute_event_hash_is_deterministic() -> None:
    args = dict(
        event_id="e1",
        event_type=AuditEventType.NOTE.value,
        client_slug="demo-co",
        actor="orchestrator",
        occurred_at=_now().isoformat(),
        payload={"x": 1},
        prev_hash=None,
    )
    assert compute_event_hash(**args) == compute_event_hash(**args)


def test_compute_event_hash_changes_with_payload() -> None:
    base = dict(
        event_id="e1",
        event_type=AuditEventType.NOTE.value,
        client_slug=None,
        actor="o",
        occurred_at=_now().isoformat(),
        prev_hash=None,
    )
    h1 = compute_event_hash(payload={"x": 1}, **base)
    h2 = compute_event_hash(payload={"x": 2}, **base)
    assert h1 != h2


def test_compute_event_hash_changes_with_prev_hash() -> None:
    base = dict(
        event_id="e1",
        event_type=AuditEventType.NOTE.value,
        client_slug=None,
        actor="o",
        occurred_at=_now().isoformat(),
        payload={},
    )
    h1 = compute_event_hash(prev_hash=None, **base)
    h2 = compute_event_hash(prev_hash="a" * 64, **base)
    assert h1 != h2


# ---------- AuditTrailEvent.build + round trip ----------

def test_build_event_round_trip() -> None:
    ev = AuditTrailEvent.build(
        event_type=AuditEventType.WORKFLOW_STARTED,
        actor="orchestrator",
        occurred_at=_now(),
        client_slug="demo-co",
        payload={"workflow": "onboarding"},
    )
    reloaded = AuditTrailEvent.from_json(ev.to_json())
    assert reloaded.model_dump() == ev.model_dump()
    assert reloaded.hash == ev.hash


def test_event_rejects_wrong_hash() -> None:
    ev = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="x",
        occurred_at=_now(),
    )
    # Mutate the JSON to inject a wrong hash.
    payload = ev.model_dump(mode="json")
    payload["hash"] = "0" * 64
    ok, errs = validate_audit_event(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.HASH_MISMATCH for e in errs)


def test_event_rejects_naive_occurred_at() -> None:
    ev = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="x",
        occurred_at=_now(),
    )
    payload = ev.model_dump(mode="json")
    payload["occurred_at"] = "2026-05-22T12:00:00"  # naive
    ok, errs = validate_audit_event(payload)
    assert ok is False


def test_event_rejects_unknown_type() -> None:
    payload = {
        "event_id": "e1",
        "event_type": "lunch_break",
        "actor": "x",
        "occurred_at": _now().isoformat(),
        "payload": {},
        "hash": "a" * 64,
    }
    ok, errs = validate_audit_event(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.INVALID_ENUM for e in errs)


def test_event_prev_hash_pattern_enforced() -> None:
    ev = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE, actor="x", occurred_at=_now()
    )
    payload = ev.model_dump(mode="json")
    payload["prev_hash"] = "not-a-hash"
    payload["hash"] = "0" * 64
    ok, errs = validate_audit_event(payload)
    assert ok is False


def test_event_requires_actor() -> None:
    payload = {
        "event_id": "e1",
        "event_type": AuditEventType.NOTE.value,
        "occurred_at": _now().isoformat(),
        "payload": {},
        "hash": "0" * 64,
    }
    ok, errs = validate_audit_event(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.MISSING_FIELD for e in errs)


def test_strict_validator_raises_with_payload() -> None:
    with pytest.raises(ContractError) as exc:
        validate_audit_event_strict({"event_type": "lunch_break"})
    assert exc.value.payload.contract == "audit-trail.v1"


# ---------- verify_chain ----------

def test_chain_valid_when_prev_hashes_match() -> None:
    e1 = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE, actor="a", occurred_at=_now()
    )
    e2 = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="a",
        occurred_at=_now(),
        prev_hash=e1.hash,
    )
    e3 = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="a",
        occurred_at=_now(),
        prev_hash=e2.hash,
    )
    assert verify_chain([e1, e2, e3]) == []


def test_chain_broken_at_index_one() -> None:
    e1 = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE, actor="a", occurred_at=_now()
    )
    # e2 declares wrong prev_hash
    e2 = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="a",
        occurred_at=_now(),
        prev_hash="b" * 64,
    )
    assert verify_chain([e1, e2]) == [1]


def test_first_event_must_have_no_prev_hash() -> None:
    # An event built with prev_hash set as the first event in a chain breaks at index 0.
    e1 = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="a",
        occurred_at=_now(),
        prev_hash="c" * 64,
    )
    assert verify_chain([e1]) == [0]


# ---------- Pydantic-level negative ----------

def test_construct_with_wrong_hash_raises() -> None:
    with pytest.raises(ValidationError):
        AuditTrailEvent(
            event_id="e1",
            event_type=AuditEventType.NOTE,
            client_slug=None,
            actor="a",
            occurred_at=_now(),
            payload={},
            prev_hash=None,
            hash="0" * 64,  # wrong
        )
