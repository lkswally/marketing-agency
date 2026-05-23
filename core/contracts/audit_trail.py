"""AuditTrailEvent — append-only event format for the audit log.

Contract: ``audit-trail.v1``

Events are linked into a hash chain so that tampering with any past entry
breaks the chain at that point. The hash is computed over a **canonical JSON**
serialization (keys sorted, no whitespace, UTF-8) of the event's core fields
plus the previous event's hash.

The model verifies the hash on construction. To build a fresh event with the
hash computed for you, use :meth:`AuditTrailEvent.build`.

This module does NOT persist anything. JSONL writing is deferred to MKT-1D.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from core.domain.base import DomainModel, new_id, validate_slug

AUDIT_TRAIL_VERSION = "audit-trail.v1"


class AuditEventType(StrEnum):
    """Vocabulary of event types appended to the trail."""

    ENVELOPE_RECEIVED = "envelope_received"
    GATE_EVALUATED = "gate_evaluated"
    PHASE_TRANSITIONED = "phase_transitioned"
    CLAIM_VERDICT = "claim_verdict"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_FINISHED = "workflow_finished"
    MEMORY_WRITTEN = "memory_written"
    ERROR_RAISED = "error_raised"
    NOTE = "note"


def _canonicalize(obj: Any) -> str:
    """Canonical JSON serialization: sorted keys, no whitespace, UTF-8.

    Required for deterministic hashing across implementations and machines.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_event_hash(
    *,
    event_id: str,
    event_type: str,
    client_slug: str | None,
    actor: str,
    occurred_at: str,
    payload: dict[str, Any],
    prev_hash: str | None,
) -> str:
    """Pure SHA256 hash of the event's canonical core.

    ``occurred_at`` is expected as an ISO 8601 string; passing the raw
    datetime would make hashes implementation-dependent.
    """
    core = {
        "contract": AUDIT_TRAIL_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "client_slug": client_slug,
        "actor": actor,
        "occurred_at": occurred_at,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(_canonicalize(core).encode("utf-8")).hexdigest()


class AuditTrailEvent(DomainModel):
    """One entry in the audit trail. Immutable once constructed.

    Construction validates that ``hash`` matches the canonical hash computed
    from the other fields. Use :meth:`build` to construct with the hash
    auto-computed.
    """

    contract_version: Literal["audit-trail.v1"] = AUDIT_TRAIL_VERSION
    event_id: str = Field(min_length=1)
    event_type: AuditEventType
    client_slug: str | None = None
    actor: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        return validate_slug(v) if v is not None else v

    @field_validator("occurred_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _hash_matches(self) -> AuditTrailEvent:
        expected = compute_event_hash(
            event_id=self.event_id,
            event_type=self.event_type.value,
            client_slug=self.client_slug,
            actor=self.actor,
            occurred_at=self.occurred_at.isoformat(),
            payload=self.payload,
            prev_hash=self.prev_hash,
        )
        if self.hash != expected:
            raise ValueError(
                f"hash mismatch: declared={self.hash!r} expected={expected!r}"
            )
        return self

    @classmethod
    def build(
        cls,
        *,
        event_type: AuditEventType,
        actor: str,
        occurred_at: datetime,
        payload: dict[str, Any] | None = None,
        client_slug: str | None = None,
        prev_hash: str | None = None,
        event_id: str | None = None,
    ) -> AuditTrailEvent:
        """Build an event with the hash computed from the supplied fields."""
        eid = event_id or new_id()
        p = payload or {}
        h = compute_event_hash(
            event_id=eid,
            event_type=event_type.value,
            client_slug=client_slug,
            actor=actor,
            occurred_at=occurred_at.isoformat(),
            payload=p,
            prev_hash=prev_hash,
        )
        return cls(
            event_id=eid,
            event_type=event_type,
            client_slug=client_slug,
            actor=actor,
            occurred_at=occurred_at,
            payload=p,
            prev_hash=prev_hash,
            hash=h,
        )


def verify_chain(events: list[AuditTrailEvent]) -> list[int]:
    """Verify a sequence of events forms a valid hash chain.

    Returns a list of indices where the chain breaks (empty list means OK).
    Pure function — no I/O.
    """
    breaks: list[int] = []
    prev: str | None = None
    for i, ev in enumerate(events):
        if ev.prev_hash != prev:
            breaks.append(i)
        prev = ev.hash
    return breaks
