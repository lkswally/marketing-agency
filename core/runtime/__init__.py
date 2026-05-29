"""MKT runtime — minimal dispatcher + agent backend interface (MKT-2A → MKT-2B)."""

from __future__ import annotations

from .backend import AgentBackend, AgentInvocation
from .backends import ClaudeCodeBackend, MockAgentBackend
from .dispatcher import (
    ENVELOPE_KIND,
    WORKFLOW_RUN_KIND,
    MinimalDispatcher,
    RunState,
)
from .errors import (
    DispatcherError,
    GateBlockingError,
    UnknownPredicate,
    WorkflowNotFound,
)
from .predicates import evaluable_kinds, evaluate, evaluate_required_gate

__all__ = [
    "MinimalDispatcher",
    "RunState",
    "ENVELOPE_KIND",
    "WORKFLOW_RUN_KIND",
    # Backends
    "AgentBackend",
    "AgentInvocation",
    "MockAgentBackend",
    "ClaudeCodeBackend",
    # Predicates
    "evaluate",
    "evaluate_required_gate",
    "evaluable_kinds",
    # Errors
    "DispatcherError",
    "WorkflowNotFound",
    "GateBlockingError",
    "UnknownPredicate",
]
