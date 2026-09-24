"""Audit trail read service (Web Foundation — read-only).

Exposes :meth:`core.memory.Memory.read_audit_events` as a filterable,
client-scoped read for a future ``GET /clients/{client_slug}/audit``
endpoint. No pagination framework and no storage redesign — this wraps
the existing per-day-JSONL read exactly as it already works
(``core/memory/json_file.py``), adding only in-memory filtering by date
range / event type / result count on top of it.

Read-only: nothing is mutated, nothing is written, nothing is audited
about the read itself (reading the audit trail does not itself need an
audit trail).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from core.contracts import AuditEventType
from core.memory import JsonFileMemory

from ..result import ErrorCode, OperationResult


def get_audit_trail(
    *,
    root: Path,
    client_slug: str,
    date_from: date | None = None,
    date_to: date | None = None,
    event_type: str | None = None,
    limit: int | None = None,
) -> OperationResult:
    """Read ``client_slug``'s audit trail, optionally filtered.

    ``date_from``/``date_to`` are inclusive UTC-day bounds (either or
    both may be given; omitted means unbounded on that side).
    ``event_type`` narrows to one :class:`AuditEventType` value.
    ``limit`` caps the number of rows returned, keeping the MOST RECENT
    ``limit`` events (the list is always chronologically ascending —
    matching :meth:`Memory.read_audit_events`'s own contract — so
    ``limit`` takes the tail, not the head).

    A client with zero events is not an error: returns an empty list.
    """
    parsed_event_type: AuditEventType | None = None
    if event_type is not None:
        try:
            parsed_event_type = AuditEventType(event_type)
        except ValueError:
            return OperationResult.error_result(
                code=ErrorCode.INVALID_INPUT,
                message=(
                    f"invalid event_type {event_type!r}; expected one of "
                    f"{', '.join(t.value for t in AuditEventType)}"
                ),
            )

    if date_from is not None and date_to is not None and date_from > date_to:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=f"date_from ({date_from}) is after date_to ({date_to})",
        )

    memory = JsonFileMemory(root)

    if date_from is not None and date_to is not None:
        # Bounded range: read only the days in it, in day order — uses
        # the storage's own per-day granularity instead of reading
        # every day on disk and discarding most of it.
        events = []
        for day in _date_range(date_from, date_to):
            events.extend(memory.read_audit_events(client_slug, day=day))
    else:
        events = memory.read_audit_events(client_slug, day=None)
        if date_from is not None:
            events = [e for e in events if e.occurred_at.date() >= date_from]
        if date_to is not None:
            events = [e for e in events if e.occurred_at.date() <= date_to]

    if parsed_event_type is not None:
        events = [e for e in events if e.event_type is parsed_event_type]

    total_matched = len(events)
    if limit is not None and limit >= 0:
        events = events[-limit:] if limit > 0 else []

    return OperationResult.ok_result(
        data={"events": events, "total_matched": total_matched},
    )


def _date_range(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


__all__ = ["get_audit_trail"]
