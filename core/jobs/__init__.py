"""Job Execution Foundation (MKT-11C).

Minimal, synchronous, in-process infrastructure for long-running
operations: contract (:mod:`.models`), explicit registry (:mod:`.registry`,
no dynamic import / no eval), persistence with full history
(:mod:`.repository`, no singleton), and a synchronous executor
(:mod:`.runner`).

**Concurrency posture:** single-process sequential use only, same as the
rest of ``core.memory`` (P-1D.3). No thread, no external queue, no lock.
See :mod:`.runner` for what the double-execution and cancellation guards
do and do not protect against.

``core.jobs`` depends on ``core.application`` (context, result, exit
codes) but never the reverse — ``core.application.services.jobs`` is what
closes that loop, one direction only.
"""

from __future__ import annotations

from .models import (
    JOB_CONTRACT_VERSION,
    JOB_KIND,
    JobError,
    JobOutcome,
    JobOutcomeStatus,
    JobRecord,
    JobState,
)
from .operations.demo import register_demo_operations
from .registry import (
    DuplicateOperationError,
    JobRegistry,
    JobRiskClass,
    OperationSpec,
    UnknownOperationError,
    default_registry,
)
from .repository import JobPersistenceError, JobRepository, sanitize_params
from .runner import InlineJobRunner, JobTransitionError

# The default registry always knows the demo operations — they are the
# only operations MKT-11C ships, and every consumer (CLI, tests importing
# core.jobs directly) should be able to run them without extra wiring.
register_demo_operations(default_registry)

__all__ = [
    "JOB_CONTRACT_VERSION",
    "JOB_KIND",
    "DuplicateOperationError",
    "InlineJobRunner",
    "JobError",
    "JobOutcome",
    "JobOutcomeStatus",
    "JobPersistenceError",
    "JobRecord",
    "JobRegistry",
    "JobRepository",
    "JobRiskClass",
    "JobState",
    "JobTransitionError",
    "OperationSpec",
    "UnknownOperationError",
    "default_registry",
    "register_demo_operations",
    "sanitize_params",
]
