"""MinimalDispatcher — MKT-2A.

Executes a :class:`WorkflowSpec` sequentially with mocked agents and the
local :class:`Memory` backend. No Claude Code, no external services, no
retry. The smallest viable runtime that exercises every contract end to end.

Per phase:
1. Evaluate ``gates_required_before`` against the run's state.
   (MKT-2A: only ``envelope_present`` is consulted; gates that are not
   declared as predicates default to "already held" once produced.)
2. For each agent declared in the phase, spawn a :class:`MockAgent` and
   collect its envelope.
3. Validate every envelope through ``validate_envelope_strict``.
4. Persist envelopes into Memory (kind=``envelope``) and append an audit
   event per envelope received.
5. Mark every ``gates_produced`` value as held in the run state.

At workflow end:
- A :class:`WorkflowRunSummary` is built and persisted (kind=``workflow_run``).
- Two audit events flank the run: ``workflow_started`` and
  ``workflow_finished``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.contracts import (
    AuditEventType,
    AuditTrailEvent,
    EnvelopeStatus,
    ReturnEnvelope,
    StepResult,
    WorkflowRunStatus,
    WorkflowRunSummary,
    validate_envelope_strict,
)
from core.domain.base import new_id, utcnow
from core.memory import Memory

from ..workflows.spec import PhaseSpec, WorkflowSpec
from .backend import AgentBackend, AgentInvocation
from .backends.mock import MockAgentBackend
from .errors import GateBlockingError
from .predicates import evaluable_kinds, evaluate_required_gate

# Memory kinds the dispatcher writes to.
ENVELOPE_KIND = "envelope"
WORKFLOW_RUN_KIND = "workflow_run"


@dataclass
class RunState:
    """In-memory state of a single workflow run."""

    run_id: str
    workflow_id: str
    client_slug: str
    envelopes: list[dict[str, Any]] = field(default_factory=list)
    held_gates: set[str] = field(default_factory=set)
    steps: list[StepResult] = field(default_factory=list)


class MinimalDispatcher:
    """Execute a workflow spec with a pluggable :class:`AgentBackend`.

    Default backend is :class:`MockAgentBackend`. Passing a backend whose
    ``run`` raises (e.g. :class:`ClaudeCodeBackend`) is allowed at construction
    time and only fails on actual execution — this lets callers wire backends
    in advance of their implementation.
    """

    def __init__(
        self,
        memory: Memory,
        agent_backend: AgentBackend | None = None,
    ) -> None:
        self._memory = memory
        self._agent_backend: AgentBackend = agent_backend or MockAgentBackend()

    # -------- public API --------

    def run(self, spec: WorkflowSpec, client_slug: str) -> WorkflowRunSummary:
        state = RunState(
            run_id=new_id(),
            workflow_id=spec.workflow_id,
            client_slug=client_slug,
        )
        started_at = utcnow()
        self._emit_audit(
            event_type=AuditEventType.WORKFLOW_STARTED,
            client_slug=client_slug,
            actor="dispatcher",
            occurred_at=started_at,
            payload={
                "run_id": state.run_id,
                "workflow_id": spec.workflow_id,
                "workflow_version": spec.version,
            },
        )

        terminal_status = WorkflowRunStatus.SUCCEEDED
        try:
            for phase in spec.phases:
                self._run_phase(spec, phase, state)
        except GateBlockingError as e:
            terminal_status = WorkflowRunStatus.FAILED
            self._record_step_failure(state, phase_id=e.phase_id, blockers=e.missing_gates)

        finished_at = utcnow()
        # If a non-FAIL step has been recorded as FAIL on a previous attempt,
        # any failed step in steps[] downgrades the run.
        if terminal_status is WorkflowRunStatus.SUCCEEDED and any(
            s.status in (EnvelopeStatus.FAIL, EnvelopeStatus.FALLIDO) for s in state.steps
        ):
            terminal_status = WorkflowRunStatus.FAILED

        summary = WorkflowRunSummary(
            run_id=state.run_id,
            workflow_name=spec.workflow_id,
            client_slug=client_slug,
            started_at=started_at,
            finished_at=finished_at,
            status=terminal_status,
            steps=state.steps,
            envelope_refs=[e["__envelope_id"] for e in state.envelopes],
            metrics={
                "duration_s": (finished_at - started_at).total_seconds(),
                "steps_total": float(len(state.steps)),
                "gates_held": float(len(state.held_gates)),
            },
        )
        self._memory.put(
            client_slug,
            WORKFLOW_RUN_KIND,
            state.run_id,
            summary.model_dump(mode="json"),
        )
        self._emit_audit(
            event_type=AuditEventType.WORKFLOW_FINISHED,
            client_slug=client_slug,
            actor="dispatcher",
            occurred_at=finished_at,
            payload={
                "run_id": state.run_id,
                "status": terminal_status.value,
                "envelope_count": len(state.envelopes),
            },
        )
        return summary

    # -------- internals --------

    def _run_phase(
        self,
        spec: WorkflowSpec,
        phase: PhaseSpec,
        state: RunState,
    ) -> None:
        missing = self._check_required_gates(phase, state)
        if missing:
            raise GateBlockingError(phase.id, missing)

        for agent_id in phase.agents:
            step_started = utcnow()
            envelope = self._agent_backend.run(
                AgentInvocation(
                    agent_id=agent_id,
                    phase_id=phase.id,
                    workflow_id=spec.workflow_id,
                    client_slug=state.client_slug,
                )
            )
            # Validate via the strict pure validator (re-checks against schema).
            validate_envelope_strict(envelope.model_dump(mode="json"))

            envelope_id = self._persist_envelope(envelope, state)
            self._record_step_success(
                state,
                phase_id=phase.id,
                agent_id=agent_id,
                envelope_id=envelope_id,
                envelope=envelope,
                started_at=step_started,
            )

        for gate in phase.gates_produced:
            state.held_gates.add(gate)

    def _check_required_gates(
        self, phase: PhaseSpec, state: RunState
    ) -> list[str]:
        """Return the list of blockers from every failing required gate.

        Delegates per-gate evaluation to :func:`predicates.evaluate_required_gate`
        so future blocks can override policy without touching the dispatcher.
        """
        blockers: list[str] = []
        for gate_name in phase.gates_required_before:
            ok, gate_blockers = evaluate_required_gate(state, gate_name)
            if not ok:
                blockers.extend(gate_blockers)
        return blockers

    def _persist_envelope(
        self, envelope: ReturnEnvelope, state: RunState
    ) -> str:
        envelope_id = new_id()
        payload = envelope.model_dump(mode="json")
        payload["__envelope_id"] = envelope_id  # dispatcher metadata
        state.envelopes.append(payload)
        self._memory.put(
            state.client_slug,
            ENVELOPE_KIND,
            envelope_id,
            payload,
        )
        self._emit_audit(
            event_type=AuditEventType.ENVELOPE_RECEIVED,
            client_slug=state.client_slug,
            actor="dispatcher",
            occurred_at=utcnow(),
            payload={
                "run_id": state.run_id,
                "envelope_id": envelope_id,
                "agent": envelope.agent,
                "status": envelope.status.value,
            },
        )
        return envelope_id

    def _record_step_success(
        self,
        state: RunState,
        *,
        phase_id: str,
        agent_id: str,
        envelope_id: str,
        envelope: ReturnEnvelope,
        started_at,
    ) -> None:
        state.steps.append(
            StepResult(
                step_id=f"{phase_id}:{agent_id}",
                agent=agent_id,
                status=envelope.status,
                envelope_id=envelope_id,
                started_at=started_at,
                finished_at=utcnow(),
                retries=0,
            )
        )

    def _record_step_failure(
        self, state: RunState, *, phase_id: str, blockers: list[str]
    ) -> None:
        now = utcnow()
        state.steps.append(
            StepResult(
                step_id=f"{phase_id}:<phase>",
                agent="dispatcher",
                status=EnvelopeStatus.FAIL,
                started_at=now,
                finished_at=now,
                retries=0,
                notes="; ".join(blockers),
            )
        )

    def _emit_audit(
        self,
        *,
        event_type: AuditEventType,
        client_slug: str,
        actor: str,
        occurred_at,
        payload: dict[str, Any],
    ) -> None:
        prev = self._memory.last_audit_hash(client_slug)
        event = AuditTrailEvent.build(
            event_type=event_type,
            actor=actor,
            occurred_at=occurred_at,
            client_slug=client_slug,
            payload=payload,
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)


# Exported helper so the CLI can show which kinds are evaluable.
__all__ = [
    "MinimalDispatcher",
    "RunState",
    "ENVELOPE_KIND",
    "WORKFLOW_RUN_KIND",
    "evaluable_kinds",
]
