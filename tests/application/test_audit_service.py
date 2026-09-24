"""Tests for the audit trail read service (Web Foundation)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from core.application.result import ErrorCode
from core.application.services.audit import get_audit_trail
from core.contracts import AuditEventType, AuditTrailEvent
from core.memory import JsonFileMemory


def _event(
    *, client_slug: str, occurred_at: datetime,
    event_type: AuditEventType = AuditEventType.NOTE,
    prev_hash: str | None = None,
) -> AuditTrailEvent:
    return AuditTrailEvent.build(
        event_type=event_type,
        actor="test",
        occurred_at=occurred_at,
        client_slug=client_slug,
        payload={"n": occurred_at.isoformat()},
        prev_hash=prev_hash,
    )


def _seed(mem: JsonFileMemory, client_slug: str, events: list[tuple]) -> None:
    """``events``: list of (occurred_at, event_type) tuples, chained in order."""
    prev = None
    for occurred_at, event_type in events:
        e = _event(
            client_slug=client_slug, occurred_at=occurred_at,
            event_type=event_type, prev_hash=prev,
        )
        mem.append_audit_event(e)
        prev = e.hash


# ---------- no events ----------

def test_no_events_returns_empty_list_not_an_error(tmp_path: Path) -> None:
    result = get_audit_trail(root=tmp_path / "mem", client_slug="acme")
    assert result.ok
    assert result.data["events"] == []
    assert result.data["total_matched"] == 0


# ---------- events exist ----------

def test_events_exist_returned_in_chronological_order(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [
        (datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 2, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 3, tzinfo=UTC), AuditEventType.NOTE),
    ])
    result = get_audit_trail(root=tmp_path / "mem", client_slug="acme")
    assert result.ok
    events = result.data["events"]
    assert len(events) == 3
    assert [e.occurred_at.day for e in events] == [1, 2, 3]
    assert result.data["total_matched"] == 3


# ---------- client isolation ----------

def test_client_isolation(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [(datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE)])
    _seed(mem, "other-client", [(datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE)])

    result_acme = get_audit_trail(root=tmp_path / "mem", client_slug="acme")
    assert len(result_acme.data["events"]) == 1
    assert result_acme.data["events"][0].client_slug == "acme"

    result_other = get_audit_trail(root=tmp_path / "mem", client_slug="other-client")
    assert len(result_other.data["events"]) == 1
    assert result_other.data["events"][0].client_slug == "other-client"


# ---------- date filter ----------

def test_date_range_filter_bounded(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [
        (datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 5, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 10, tzinfo=UTC), AuditEventType.NOTE),
    ])
    result = get_audit_trail(
        root=tmp_path / "mem", client_slug="acme",
        date_from=date(2026, 1, 3), date_to=date(2026, 1, 8),
    )
    assert result.ok
    events = result.data["events"]
    assert len(events) == 1
    assert events[0].occurred_at.day == 5


def test_date_from_only(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [
        (datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 5, tzinfo=UTC), AuditEventType.NOTE),
    ])
    result = get_audit_trail(root=tmp_path / "mem", client_slug="acme", date_from=date(2026, 1, 3))
    assert [e.occurred_at.day for e in result.data["events"]] == [5]


def test_invalid_date_range_rejected(tmp_path: Path) -> None:
    result = get_audit_trail(
        root=tmp_path / "mem", client_slug="acme",
        date_from=date(2026, 1, 10), date_to=date(2026, 1, 1),
    )
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


# ---------- event type filter ----------

def test_event_type_filter(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [
        (datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 2, tzinfo=UTC), AuditEventType.MEMORY_WRITTEN),
        (datetime(2026, 1, 3, tzinfo=UTC), AuditEventType.NOTE),
    ])
    result = get_audit_trail(
        root=tmp_path / "mem", client_slug="acme", event_type="memory_written",
    )
    assert result.ok
    events = result.data["events"]
    assert len(events) == 1
    assert events[0].event_type is AuditEventType.MEMORY_WRITTEN


def test_invalid_event_type_rejected(tmp_path: Path) -> None:
    result = get_audit_trail(root=tmp_path / "mem", client_slug="acme", event_type="not-a-real-type")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


# ---------- limit ----------

def test_limit_keeps_most_recent(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [
        (datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 2, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 3, tzinfo=UTC), AuditEventType.NOTE),
    ])
    result = get_audit_trail(root=tmp_path / "mem", client_slug="acme", limit=2)
    assert result.ok
    events = result.data["events"]
    assert [e.occurred_at.day for e in events] == [2, 3]
    # total_matched reflects the pre-limit count, so a caller can tell
    # there were more rows than were returned.
    assert result.data["total_matched"] == 3


def test_limit_zero_returns_no_events(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [(datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE)])
    result = get_audit_trail(root=tmp_path / "mem", client_slug="acme", limit=0)
    assert result.ok
    assert result.data["events"] == []
    assert result.data["total_matched"] == 1


# ---------- no mutation ----------

def test_read_never_mutates_the_stored_chain(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed(mem, "acme", [
        (datetime(2026, 1, 1, tzinfo=UTC), AuditEventType.NOTE),
        (datetime(2026, 1, 2, tzinfo=UTC), AuditEventType.NOTE),
    ])
    tail_before = mem.last_audit_hash("acme")
    get_audit_trail(root=tmp_path / "mem", client_slug="acme")
    get_audit_trail(root=tmp_path / "mem", client_slug="acme", limit=1)
    get_audit_trail(root=tmp_path / "mem", client_slug="acme", event_type="note")
    tail_after = mem.last_audit_hash("acme")
    assert tail_before == tail_after
