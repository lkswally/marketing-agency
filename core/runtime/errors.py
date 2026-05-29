"""Runtime errors for the minimal dispatcher."""

from __future__ import annotations


class DispatcherError(Exception):
    """Base error raised by the dispatcher."""


class WorkflowNotFound(DispatcherError):  # noqa: N818  (idiomatic naming)
    """Raised when ``run`` is called with an unknown ``workflow_id``."""


class GateBlockingError(DispatcherError):
    """Raised when a phase cannot run because required gates are missing."""

    def __init__(self, phase_id: str, missing_gates: list[str]) -> None:
        self.phase_id = phase_id
        self.missing_gates = missing_gates
        super().__init__(
            f"phase {phase_id!r} blocked: missing gates={missing_gates}"
        )


class UnknownPredicate(DispatcherError):  # noqa: N818  (idiomatic naming)
    """Raised when a workflow consumes a predicate kind not yet evaluated."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(
            f"predicate_kind {kind!r} is not evaluated by the MKT-2A dispatcher"
        )
