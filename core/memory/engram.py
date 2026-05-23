"""EngramMemory — scaffolding only. Not connected.

Activated in the future by setting ``MKT_MEMORY_BACKEND=engram`` (see
``ARCHITECTURE.md`` D2). Until MKT-2C ships the real adapter, every method
raises :class:`NotImplementedError` with a pointer to the work that will
implement it.

This module deliberately does NOT import any Engram SDK or MCP client. It
exists so that downstream callers can be written against the abstract
:class:`Memory` interface today without depending on a backend that does not
exist yet.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.contracts import AuditTrailEvent

from .base import Memory

_NOT_IMPLEMENTED_MSG = (
    "EngramMemory is scaffolding only — the real connector is scheduled for "
    "MKT-2C. Use JsonFileMemory or set MKT_MEMORY_BACKEND=json for now."
)


class EngramMemory(Memory):
    """Future Engram-backed :class:`Memory`. Not implemented in MKT-1D."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept any constructor args silently so callers can be wired in
        # advance; we only fail when someone actually tries to use it.
        self._args = args
        self._kwargs = kwargs

    # -------- entity CRUD --------

    def put(
        self, client_slug: str, kind: str, entity_id: str, data: dict[str, Any]
    ) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def get(self, client_slug: str, kind: str, entity_id: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def list(self, client_slug: str, kind: str) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def exists(self, client_slug: str, kind: str, entity_id: str) -> bool:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def delete(self, client_slug: str, kind: str, entity_id: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    # -------- audit trail --------

    def append_audit_event(self, event: AuditTrailEvent) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def read_audit_events(
        self, client_slug: str, day: date | None = None
    ) -> list[AuditTrailEvent]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def last_audit_hash(self, client_slug: str) -> str | None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
