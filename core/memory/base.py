"""Abstract :class:`Memory` interface and supporting types.

The interface is intentionally generic: every operation takes a string
``client_slug`` (multi-tenant scope), a string ``kind`` (entity type, e.g.
``"client"``, ``"campaign"``), and either an entity id or a payload dict.

The layer is **domain-agnostic** — it does not import ``core.domain``. Typed
access (Pydantic models in / out) is the job of a future repository layer.

Contract: ``memory.v1`` (see ``docs/contracts/memory.md``).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date
from typing import Any

from core.contracts import AuditTrailEvent

MEMORY_CONTRACT_VERSION = "memory.v1"

# A "kind" is the entity type as a flat string identifier. Allowed characters
# match the domain glossary; rejecting anything else prevents accidental
# directory traversal via crafted ``kind`` values.
_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_kind(kind: str) -> str:
    """Validate a kind label.

    Raises:
        ValueError: if ``kind`` does not match ``[a-z][a-z0-9_]{0,63}``.
    """
    if not isinstance(kind, str) or not _KIND_RE.match(kind):
        raise ValueError(
            f"invalid kind {kind!r}: must match [a-z][a-z0-9_]{{0,63}}"
        )
    return kind


class Memory(ABC):
    """Multi-tenant key-value store for MKT entities plus an append-only audit log.

    Implementations MUST be safe for sequential single-process use. Concurrent
    multi-process safety is out of scope for ``memory.v1``.
    """

    # -------- entity CRUD --------

    @abstractmethod
    def put(
        self, client_slug: str, kind: str, entity_id: str, data: dict[str, Any]
    ) -> None:
        """Persist (or overwrite) the entity payload."""

    @abstractmethod
    def get(self, client_slug: str, kind: str, entity_id: str) -> dict[str, Any]:
        """Return the persisted payload.

        Raises:
            EntityNotFound: if no entity exists at this coordinate.
        """

    @abstractmethod
    def list(self, client_slug: str, kind: str) -> list[dict[str, Any]]:
        """Return every entity payload for ``(client_slug, kind)``.

        Ordering is stable but unspecified (implementations may sort by id).
        Empty list if the kind has no entities.
        """

    @abstractmethod
    def exists(self, client_slug: str, kind: str, entity_id: str) -> bool:
        """True if an entity exists at this coordinate."""

    @abstractmethod
    def delete(self, client_slug: str, kind: str, entity_id: str) -> None:
        """Remove the entity.

        Raises:
            EntityNotFound: if no entity exists at this coordinate.
        """

    # -------- audit trail --------

    @abstractmethod
    def append_audit_event(self, event: AuditTrailEvent) -> None:
        """Append an audit event for ``event.client_slug``.

        Storage-level requirement: ``event.client_slug`` MUST be set (the
        contract allows ``None`` but the storage layer rejects it).

        Raises:
            ValueError: if ``event.client_slug`` is None.
            AuditChainError: if the event's ``prev_hash`` disagrees with the
                last persisted hash for this client.
        """

    @abstractmethod
    def read_audit_events(
        self, client_slug: str, day: date | None = None
    ) -> list[AuditTrailEvent]:
        """Read audit events for a client.

        ``day``: when given, read only that UTC day's JSONL. When ``None``,
        concatenate every day in chronological order.
        """

    @abstractmethod
    def last_audit_hash(self, client_slug: str) -> str | None:
        """Return the hash of the last appended audit event for this client.

        ``None`` when no event has been appended yet.
        """

    def append_audit_event_atomic(
        self, client_slug: str, build_event: Callable[[str | None], AuditTrailEvent],
    ) -> AuditTrailEvent:
        """Read the current chain tail, build the event from it via
        ``build_event(prev_hash)``, and append it, all as one atomic unit
        with respect to other concurrent callers for the same
        ``client_slug`` (job-execution-robustness).

        This closes a race :meth:`append_audit_event` alone cannot: a
        caller that reads :meth:`last_audit_hash` and builds its event
        *before* calling :meth:`append_audit_event` can lose a race to
        another concurrent writer between that read and its own append.
        Here, the read and the append happen under the same exclusivity.

        Default implementation (correct, but NOT concurrency-safe —
        provided so this stays a non-abstract, backward-compatible
        addition to the interface rather than a breaking change to every
        implementer): backends that need a real concurrency guarantee
        (currently only :class:`~core.memory.json_file.JsonFileMemory`)
        override this. Backends that don't override it inherit whatever
        concurrency posture their own :meth:`append_audit_event` has.
        """
        event = build_event(self.last_audit_hash(client_slug))
        self.append_audit_event(event)
        return event
