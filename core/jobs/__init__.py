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
from .runner import InlineJobRunner, JobStartError, JobTransitionError

# The default registry always knows the demo operations — they only
# depend on core.application.context/result (leaf modules), so
# registering them here at core.jobs import time is safe.
#
# campaign.run (MKT-11D) is deliberately NOT registered here: its handler
# depends on core.application.services.campaign_run, and
# core.application.services.__init__ itself imports core.application.
# services.jobs, which imports core.jobs — registering campaign.run from
# inside core/jobs/__init__.py would make `import core.jobs` (with
# nothing else imported first) circular. It is registered instead from
# core/application/services/jobs.py, which by construction only ever
# finishes importing core.jobs (this module) before it runs, at which
# point importing core.application.services.campaign_run back is safe.
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
    "JobStartError",
    "JobTransitionError",
    "OperationSpec",
    "UnknownOperationError",
    "default_registry",
    "register_demo_operations",
    "sanitize_params",
]
