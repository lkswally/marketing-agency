"""Explicit operation registry (MKT-11C).

No dynamic import, no resolution by function name, no ``eval``. An
operation is executable only if a :class:`OperationSpec` for it was
registered ahead of time — the registry is the single choke point that
prevents "run arbitrary code by name."

:class:`JobRegistry` is an instantiable class, not a module-level dict —
tests get their own isolated registry; :data:`default_registry` is the
one convenience instance the CLI and services use in practice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from core.application.context import OperationContext

from .models import JobOutcome

JobHandler = Callable[[OperationContext, BaseModel], JobOutcome]


class JobRiskClass(StrEnum):
    """Advisory classification — MKT-11C does not gate execution on this
    (that is autonomy-policy territory, §24/§14B of the master plan). It
    exists now so operations registered in this milestone don't need a
    contract change when policy enforcement lands."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class OperationSpec:
    """One registrable unit of executable work."""

    operation: str
    """Stable id, e.g. ``"demo.echo"``. Dotted namespace by convention —
    not structurally enforced."""

    params_model: type[BaseModel]
    """Every param dict is validated against this model before a
    :class:`~core.jobs.models.JobRecord` is even created."""

    handler: JobHandler
    risk_class: JobRiskClass
    description: str

    sensitive_param_fields: frozenset[str] = frozenset()
    """Field names on ``params_model`` whose values must never reach
    persisted storage verbatim. :func:`core.jobs.repository.sanitize_params`
    replaces each with a fixed redaction marker before the JobRecord is
    written. Empty by default — MKT-11C ships no operation that touches a
    credential, but this is the contract point future connectors (GA4,
    Google Ads, Meta Ads tokens) must populate instead of inventing their
    own redaction."""

    dev_only: bool = False
    """True for operations that exist to exercise the job lifecycle in
    tests (e.g. ``demo.needs_approval``) and must never be treated as
    production capability. The registry does not refuse to run them (a
    test needs to run them) — CLI help text and any future operation
    listing must visibly flag them, so a dev_only operation is never
    mistaken for a real one."""


class UnknownOperationError(LookupError):
    """Raised by :meth:`JobRegistry.resolve` for an unregistered operation.
    Callers map this to ``ErrorCode.UNKNOWN_OPERATION`` — never let it
    propagate as a raw traceback."""


class DuplicateOperationError(ValueError):
    """Raised by :meth:`JobRegistry.register` when ``operation`` is already
    registered — registration order must not silently decide behaviour."""


class JobRegistry:
    """In-memory table of operation id -> :class:`OperationSpec`."""

    def __init__(self) -> None:
        self._specs: dict[str, OperationSpec] = {}

    def register(self, spec: OperationSpec) -> None:
        if spec.operation in self._specs:
            raise DuplicateOperationError(
                f"operation {spec.operation!r} is already registered"
            )
        self._specs[spec.operation] = spec

    def resolve(self, operation: str) -> OperationSpec:
        try:
            return self._specs[operation]
        except KeyError:
            raise UnknownOperationError(
                f"no operation registered as {operation!r}"
            ) from None

    def is_registered(self, operation: str) -> bool:
        return operation in self._specs

    def list_operations(self) -> list[OperationSpec]:
        """Stable order: by operation id, ascending."""
        return [self._specs[k] for k in sorted(self._specs)]


default_registry = JobRegistry()
"""The registry the CLI and application services use unless a caller
explicitly injects its own (as every test in this package does)."""


__all__ = [
    "DuplicateOperationError",
    "JobHandler",
    "JobRegistry",
    "JobRiskClass",
    "OperationSpec",
    "UnknownOperationError",
    "default_registry",
]
