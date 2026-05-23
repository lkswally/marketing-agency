"""ContractError — shared error structure across MKT contracts.

A single error is both an exception (raise) and a Pydantic payload (return /
serialize). Validators in :mod:`core.contracts.validators` come in two flavors:

- non-strict: return ``(ok, list[ContractErrorPayload])``
- ``_strict``: raise the first ``ContractError`` they find
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from core.domain.base import DomainModel


class ContractErrorCode(StrEnum):
    """Catalogue of contract-violation codes.

    Stable identifiers — values may be referenced by name in audit trails.
    """

    MISSING_FIELD = "missing_field"
    INVALID_TYPE = "invalid_type"
    INVALID_ENUM = "invalid_enum"
    EXTRA_FIELD = "extra_field"
    INVARIANT_VIOLATION = "invariant_violation"
    VERSION_MISMATCH = "version_mismatch"
    HASH_MISMATCH = "hash_mismatch"
    DUPLICATE_REF = "duplicate_ref"
    NAIVE_DATETIME = "naive_datetime"
    SCHEMA_ERROR = "schema_error"
    UNKNOWN = "unknown"


class ContractErrorPayload(DomainModel):
    """Serializable representation of a contract violation."""

    code: ContractErrorCode
    contract: str = Field(min_length=1)  # e.g. "envelope.v1"
    path: str = ""  # JSON-pointer-ish location of the problem
    message: str = Field(min_length=1)
    details: dict[str, str] = Field(default_factory=dict)


class ContractError(Exception):
    """Raised by ``_strict`` validators when a contract is violated."""

    def __init__(self, payload: ContractErrorPayload) -> None:
        self.payload = payload
        super().__init__(
            f"[{payload.contract}] {payload.code.value} @ "
            f"{payload.path or '<root>'}: {payload.message}"
        )
