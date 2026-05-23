"""ReturnEnvelope — standard response shape every agent must emit.

Contract: ``envelope.v1``

The envelope is the universal handoff between an agent and the dispatcher (and
between the dispatcher and the audit trail). It carries status, references to
produced artifacts and memory writes, and an optional ClaimAudit block when
the output contains factual claims.

Validators in :mod:`core.contracts.validators` support multiple strictness
modes (see ``docs/contracts/return-envelope.md`` for the matrix).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.domain.base import DomainModel, validate_slug

from .claim_audit import ClaimAudit

ENVELOPE_VERSION = "envelope.v1"


class EnvelopeStatus(StrEnum):
    """Allowed envelope status values.

    ``PASS`` / ``FAIL`` are reserved for validator-type agents (QA, claim
    validator, reality-checker). Generic agents use ``completado`` / ``fallido``.
    """

    COMPLETADO = "completado"
    FALLIDO = "fallido"
    PASS = "PASS"
    FAIL = "FAIL"


# Status values that indicate failure.
_FAILURE_STATUSES = frozenset({EnvelopeStatus.FALLIDO, EnvelopeStatus.FAIL})


class ArtifactKind(StrEnum):
    FILE = "file"
    MEMORY = "memory"
    URL = "url"
    INLINE = "inline"


class ArtifactRef(DomainModel):
    """Reference to a single artifact produced by an agent.

    Artifacts are described by location and (optionally) by hash. The agent is
    responsible for putting the file on disk or memory; the envelope only
    points to it.
    """

    path: str = Field(min_length=1)
    kind: ArtifactKind
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    bytes: int | None = Field(default=None, ge=0)
    description: str | None = None


class MemoryWriteRef(DomainModel):
    """Reference to a topic_key that the agent wrote to memory."""

    topic_key: str = Field(min_length=1)
    backend: Literal["json", "engram", "memory"]
    bytes: int | None = Field(default=None, ge=0)


class ReturnEnvelope(DomainModel):
    """Standard agent response.

    Required fields: ``status``, ``agent``, ``task``, ``produced_at``.

    Failure semantics: when ``status`` is ``FALLIDO`` or ``FAIL`` the envelope
    MUST carry at least one ``bloqueadores`` entry or a non-empty ``notes``
    field, so the audit trail records why.
    """

    contract_version: Literal["envelope.v1"] = ENVELOPE_VERSION
    status: EnvelopeStatus
    agent: str = Field(min_length=1, max_length=200)
    task: str = Field(min_length=1)
    client_slug: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    memory_writes: list[MemoryWriteRef] = Field(default_factory=list)
    claims_audit: ClaimAudit | None = None
    bloqueadores: list[str] = Field(default_factory=list)
    notes: str | None = None
    produced_at: datetime

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        return validate_slug(v) if v is not None else v

    @field_validator("produced_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("produced_at must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _failure_requires_explanation(self) -> ReturnEnvelope:
        if self.status in _FAILURE_STATUSES and not self.bloqueadores and not self.notes:
            raise ValueError(
                f"envelope with status={self.status.value} requires "
                "at least one bloqueadores entry or notes"
            )
        return self

    @model_validator(mode="after")
    def _memory_topic_keys_unique(self) -> ReturnEnvelope:
        keys = [w.topic_key for w in self.memory_writes]
        if len(keys) != len(set(keys)):
            raise ValueError("memory_writes contain duplicate topic_key entries")
        return self
