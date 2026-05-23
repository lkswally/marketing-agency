"""MKT operational contracts.

Each contract is versioned independently. Importable surface:

- Models: :class:`ReturnEnvelope`, :class:`PhaseGate`, :class:`PhaseGateResult`,
  :class:`PhaseTransition`, :class:`AuditTrailEvent`, :class:`ClaimAudit`,
  :class:`WorkflowRunSummary`.
- Pure validators: see :mod:`core.contracts.validators`.
- Errors: :class:`ContractError`, :class:`ContractErrorPayload`,
  :class:`ContractErrorCode`.
"""

from __future__ import annotations

from .audit_trail import (
    AUDIT_TRAIL_VERSION,
    AuditEventType,
    AuditTrailEvent,
    compute_event_hash,
    verify_chain,
)
from .claim_audit import (
    CLAIM_AUDIT_VERSION,
    ClaimAudit,
    ClaimAuditItem,
    EvidenceRef,
    severity_rank,
)
from .envelope import (
    ENVELOPE_VERSION,
    ArtifactKind,
    ArtifactRef,
    EnvelopeStatus,
    MemoryWriteRef,
    ReturnEnvelope,
)
from .errors import ContractError, ContractErrorCode, ContractErrorPayload
from .phase_gate import (
    PHASE_GATE_VERSION,
    GateSeverity,
    PhaseGate,
    PhaseGateResult,
    PhaseTransition,
    PredicateKind,
)
from .validators import (
    validate_audit_event,
    validate_audit_event_strict,
    validate_claim_audit,
    validate_claim_audit_strict,
    validate_envelope,
    validate_envelope_strict,
    validate_phase_gate,
    validate_phase_gate_result,
    validate_phase_transition,
    validate_phase_transition_strict,
    validate_workflow_run,
    validate_workflow_run_strict,
)
from .workflow_run import (
    WORKFLOW_RUN_VERSION,
    StepResult,
    WorkflowRunStatus,
    WorkflowRunSummary,
)

__all__ = [
    # Versions
    "ENVELOPE_VERSION",
    "PHASE_GATE_VERSION",
    "AUDIT_TRAIL_VERSION",
    "CLAIM_AUDIT_VERSION",
    "WORKFLOW_RUN_VERSION",
    # Envelope
    "ReturnEnvelope",
    "EnvelopeStatus",
    "ArtifactRef",
    "ArtifactKind",
    "MemoryWriteRef",
    # ClaimAudit
    "ClaimAudit",
    "ClaimAuditItem",
    "EvidenceRef",
    "severity_rank",
    # PhaseGate
    "PhaseGate",
    "PhaseGateResult",
    "PhaseTransition",
    "PredicateKind",
    "GateSeverity",
    # AuditTrail
    "AuditTrailEvent",
    "AuditEventType",
    "compute_event_hash",
    "verify_chain",
    # WorkflowRun
    "WorkflowRunSummary",
    "WorkflowRunStatus",
    "StepResult",
    # Errors
    "ContractError",
    "ContractErrorCode",
    "ContractErrorPayload",
    # Validators
    "validate_envelope",
    "validate_envelope_strict",
    "validate_claim_audit",
    "validate_claim_audit_strict",
    "validate_phase_gate",
    "validate_phase_gate_result",
    "validate_phase_transition",
    "validate_phase_transition_strict",
    "validate_audit_event",
    "validate_audit_event_strict",
    "validate_workflow_run",
    "validate_workflow_run_strict",
]
