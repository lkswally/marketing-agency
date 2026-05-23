"""MKT memory / storage layer.

Contract: ``memory.v1`` (see ``docs/contracts/memory.md``).

Importable surface:

- Interface: :class:`Memory`.
- Backends: :class:`JsonFileMemory` (default), :class:`EngramMemory` (scaffold).
- Errors: :class:`MemoryBackendError`, :class:`EntityNotFound`,
  :class:`IntegrityError`, :class:`AuditChainError`.
- Referential integrity: :class:`ReferenceRule`, :class:`MissingReference`,
  :func:`find_missing_references`, :func:`check_client_integrity`,
  :data:`REFERENCE_MAP`, :data:`ALL_KINDS`.
"""

from __future__ import annotations

from .base import MEMORY_CONTRACT_VERSION, Memory, validate_kind
from .engram import EngramMemory
from .errors import AuditChainError, EntityNotFound, IntegrityError, MemoryBackendError
from .json_file import JsonFileMemory
from .referential_integrity import (
    ALL_KINDS,
    REFERENCE_MAP,
    MissingReference,
    ReferenceRule,
    check_client_integrity,
    find_missing_references,
)

__all__ = [
    "MEMORY_CONTRACT_VERSION",
    "Memory",
    "validate_kind",
    "JsonFileMemory",
    "EngramMemory",
    "MemoryBackendError",
    "EntityNotFound",
    "IntegrityError",
    "AuditChainError",
    "ReferenceRule",
    "MissingReference",
    "REFERENCE_MAP",
    "ALL_KINDS",
    "find_missing_references",
    "check_client_integrity",
]
