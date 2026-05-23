"""Tests for the JSONL audit trail backed by JsonFileMemory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.contracts import AuditEventType, AuditTrailEvent, verify_chain
from core.memory import AuditChainError, JsonFileMemory


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


def _event(
    occurred_at: datetime,
    prev_hash: str | None = None,
    client_slug: str | None = "demo-co",
    payload: dict | None = None,
) -> AuditTrailEvent:
    return AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="orchestrator",
        occurred_at=occurred_at,
        client_slug=client_slug,
        payload=payload or {},
        prev_hash=prev_hash,
    )


# ---------- append + last_hash ----------

def test_first_append_creates_file_and_tail(mem: JsonFileMemory, tmp_path: Path) -> None:
    ev = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC))
    mem.append_audit_event(ev)
    day_file = tmp_path / "demo-co" / "audit" / "2026-05-22.jsonl"
    tail_file = tmp_path / "demo-co" / "audit" / "_chain_tail.txt"
    assert day_file.exists()
    assert tail_file.exists()
    assert tail_file.read_text().strip() == ev.hash
    assert mem.last_audit_hash("demo-co") == ev.hash


def test_no_events_returns_none_tail(mem: JsonFileMemory) -> None:
    assert mem.last_audit_hash("demo-co") is None


# ---------- chain enforcement ----------

def test_second_event_must_use_prev_hash(mem: JsonFileMemory) -> None:
    e1 = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC))
    mem.append_audit_event(e1)
    e2 = _event(datetime(2026, 5, 22, 12, 1, tzinfo=UTC), prev_hash=e1.hash)
    mem.append_audit_event(e2)
    assert mem.last_audit_hash("demo-co") == e2.hash


def test_wrong_prev_hash_rejected(mem: JsonFileMemory) -> None:
    e1 = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC))
    mem.append_audit_event(e1)
    bad = _event(datetime(2026, 5, 22, 12, 1, tzinfo=UTC), prev_hash="a" * 64)
    with pytest.raises(AuditChainError):
        mem.append_audit_event(bad)


def test_first_event_must_have_no_prev_hash(mem: JsonFileMemory) -> None:
    bad = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC), prev_hash="b" * 64)
    with pytest.raises(AuditChainError):
        mem.append_audit_event(bad)


# ---------- append-only semantics ----------

def test_appending_does_not_truncate(mem: JsonFileMemory, tmp_path: Path) -> None:
    e1 = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC), payload={"n": 1})
    mem.append_audit_event(e1)
    e2 = _event(datetime(2026, 5, 22, 12, 1, tzinfo=UTC), prev_hash=e1.hash, payload={"n": 2})
    mem.append_audit_event(e2)
    day_file = tmp_path / "demo-co" / "audit" / "2026-05-22.jsonl"
    lines = day_file.read_text().splitlines()
    assert len(lines) == 2


# ---------- daily rotation ----------

def test_day_rotation_creates_second_file(mem: JsonFileMemory, tmp_path: Path) -> None:
    e1 = _event(datetime(2026, 5, 22, 23, 59, tzinfo=UTC))
    mem.append_audit_event(e1)
    e2 = _event(datetime(2026, 5, 23, 0, 1, tzinfo=UTC), prev_hash=e1.hash)
    mem.append_audit_event(e2)
    audit_dir = tmp_path / "demo-co" / "audit"
    files = sorted(p.name for p in audit_dir.glob("*.jsonl"))
    assert files == ["2026-05-22.jsonl", "2026-05-23.jsonl"]


# ---------- read_audit_events ----------

def test_read_all_returns_in_chronological_order(mem: JsonFileMemory) -> None:
    events = []
    t = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    prev = None
    for i in range(3):
        ev = _event(t + timedelta(minutes=i), prev_hash=prev, payload={"i": i})
        mem.append_audit_event(ev)
        events.append(ev)
        prev = ev.hash
    read = mem.read_audit_events("demo-co")
    assert [e.hash for e in read] == [e.hash for e in events]


def test_read_specific_day(mem: JsonFileMemory) -> None:
    e1 = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC))
    mem.append_audit_event(e1)
    e2 = _event(datetime(2026, 5, 23, 12, 0, tzinfo=UTC), prev_hash=e1.hash)
    mem.append_audit_event(e2)
    only_22 = mem.read_audit_events("demo-co", day=e1.occurred_at.date())
    assert [e.hash for e in only_22] == [e1.hash]


def test_read_chain_verifies(mem: JsonFileMemory) -> None:
    t = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    prev = None
    for i in range(4):
        ev = _event(t + timedelta(minutes=i), prev_hash=prev, payload={"i": i})
        mem.append_audit_event(ev)
        prev = ev.hash
    assert verify_chain(mem.read_audit_events("demo-co")) == []


# ---------- corruption ----------

def test_corrupt_jsonl_raises_chain_error(mem: JsonFileMemory, tmp_path: Path) -> None:
    e1 = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC))
    mem.append_audit_event(e1)
    day_file = tmp_path / "demo-co" / "audit" / "2026-05-22.jsonl"
    with day_file.open("a", encoding="utf-8") as f:
        f.write("not-json\n")
    with pytest.raises(AuditChainError):
        mem.read_audit_events("demo-co")


# ---------- storage requires client_slug ----------

def test_event_without_client_slug_rejected(mem: JsonFileMemory) -> None:
    ev = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC), client_slug=None)
    with pytest.raises(ValueError):
        mem.append_audit_event(ev)


# ---------- read empty ----------

def test_read_empty_returns_empty(mem: JsonFileMemory) -> None:
    assert mem.read_audit_events("demo-co") == []


# ---------- multi-tenant audit isolation ----------

def test_clients_have_isolated_chains(mem: JsonFileMemory) -> None:
    a = _event(datetime(2026, 5, 22, 12, 0, tzinfo=UTC), client_slug="acme")
    b = _event(datetime(2026, 5, 22, 12, 1, tzinfo=UTC), client_slug="demo-co")
    mem.append_audit_event(a)
    mem.append_audit_event(b)
    assert mem.last_audit_hash("acme") == a.hash
    assert mem.last_audit_hash("demo-co") == b.hash
