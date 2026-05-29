"""MKT runtime — minimal dispatcher + mock agent (MKT-2A)."""

from __future__ import annotations

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
from .mock_agent import MockAgent, MockAgentInput
from .predicates import evaluable_kinds, evaluate

__all__ = [
    "MinimalDispatcher",
    "RunState",
    "ENVELOPE_KIND",
    "WORKFLOW_RUN_KIND",
    "MockAgent",
    "MockAgentInput",
    "evaluate",
    "evaluable_kinds",
    "DispatcherError",
    "WorkflowNotFound",
    "GateBlockingError",
    "UnknownPredicate",
]
