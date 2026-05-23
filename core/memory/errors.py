"""Exception hierarchy for the MKT memory layer.

We deliberately do NOT name the base ``MemoryError`` because Python's builtin
:class:`MemoryError` (out-of-memory) lives in that name.
"""

from __future__ import annotations


class MemoryBackendError(Exception):
    """Base error raised by any memory backend."""


class EntityNotFound(MemoryBackendError):  # noqa: N818  (idiomatic naming, mirrors SQLAlchemy NoResultFound)
    """Raised by ``get`` / ``delete`` when the entity does not exist."""

    def __init__(self, client_slug: str, kind: str, entity_id: str) -> None:
        self.client_slug = client_slug
        self.kind = kind
        self.entity_id = entity_id
        super().__init__(
            f"entity not found: client_slug={client_slug!r} kind={kind!r} id={entity_id!r}"
        )


class IntegrityError(MemoryBackendError):
    """Raised when storage invariants are violated (kind mismatch, etc.)."""


class AuditChainError(MemoryBackendError):
    """Raised when the audit JSONL or chain tail is corrupted or inconsistent."""
