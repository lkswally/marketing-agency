"""PhaseGate — predicate evaluated between workflow phases.

Contract: ``phase-gate.v1``

A gate is the **declaration** of a check; a :class:`PhaseGateResult` is the
**outcome** of evaluating that check on concrete data. A
:class:`PhaseTransition` bundles results to decide whether a phase advances.

The model is descriptive — it does NOT evaluate anything. Evaluation lives in
the future dispatcher (MKT-2A+).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.domain.base import DomainModel

PHASE_GATE_VERSION = "phase-gate.v1"


class GateSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


class PredicateKind(StrEnum):
    """Catalogue of declarative predicate kinds.

    Each predicate kind names a class of check the future dispatcher will
    know how to evaluate. ``params`` on the gate carries kind-specific
    arguments. Adding a kind here is intentionally cheap (additive change
    within ``phase-gate.v1``); removing one is breaking.
    """

    ENVELOPE_PRESENT = "envelope_present"
    STATUS_EQUALS = "status_equals"
    CLAIMS_AUDIT_PRESENT = "claims_audit_present"
    NO_UNSAFE_CLAIMS = "no_unsafe_claims"
    MEMORY_KEY_EXISTS = "memory_key_exists"
    ARTIFACT_EXISTS = "artifact_exists"
    CUSTOM = "custom"


class PhaseGate(DomainModel):
    """Declaration of a check that gates a phase transition."""

    contract_version: Literal["phase-gate.v1"] = PHASE_GATE_VERSION
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    phase: str = Field(min_length=1, max_length=200)
    predicate_kind: PredicateKind
    params: dict[str, str] = Field(default_factory=dict)
    severity: GateSeverity = GateSeverity.BLOCKING
    description: str | None = None


class PhaseGateResult(DomainModel):
    """Outcome of evaluating a :class:`PhaseGate`."""

    contract_version: Literal["phase-gate.v1"] = PHASE_GATE_VERSION
    gate_id: str = Field(min_length=1)
    passed: bool
    blockers: list[str] = Field(default_factory=list)
    evaluated_at: datetime
    details: dict[str, str] = Field(default_factory=dict)

    @field_validator("evaluated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _failed_needs_blockers(self) -> PhaseGateResult:
        if not self.passed and not self.blockers:
            raise ValueError("failed gate result must include at least one blocker")
        return self


class PhaseTransition(DomainModel):
    """Bundle of gate results evaluated together for a phase transition."""

    contract_version: Literal["phase-gate.v1"] = PHASE_GATE_VERSION
    from_phase: str = Field(min_length=1)
    to_phase: str = Field(min_length=1)
    gate_results: list[PhaseGateResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicate_gates(self) -> PhaseTransition:
        ids = [r.gate_id for r in self.gate_results]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate gate_id in transition.gate_results")
        return self

    @property
    def passed(self) -> bool:
        """True when every gate result passed."""
        return all(r.passed for r in self.gate_results)
