"""Predicate evaluators for phase-gate kinds + the dispatcher's gate check.

MKT-2A introduced ``envelope_present``. MKT-2B adds ``status_equals`` and
the central :func:`evaluate_required_gate` helper the dispatcher now calls
for every consumed gate (replacing the inline ``gate in held_gates`` check
of MKT-2A).

The default policy of :func:`evaluate_required_gate` is unchanged: a gate
is held iff a prior phase declared it as produced. Future blocks may
override the policy per gate (e.g. ``no_unsafe_claims`` would re-scan
envelopes rather than trusting the set).
"""

from __future__ import annotations

from collections.abc import Callable

from core.contracts import PredicateKind

from .errors import UnknownPredicate


# Forward-ref placeholder for typing; the real ``RunState`` lives in dispatcher.
class RunState:  # pragma: no cover - structural placeholder
    envelopes: list[dict]
    held_gates: set[str]


# A predicate evaluator returns (passed, blockers).
PredicateFn = Callable[[RunState, dict[str, str]], tuple[bool, list[str]]]


def _envelope_present(state: RunState, params: dict[str, str]) -> tuple[bool, list[str]]:
    """``envelope_present`` — the named agent has produced an envelope in this run."""
    agent = params.get("agent", "").strip()
    if not agent:
        return False, ["predicate_kind=envelope_present requires params.agent"]
    matched = [env for env in state.envelopes if env["agent"] == agent]
    if not matched:
        return False, [f"no envelope from agent={agent!r} in this run"]
    return True, []


def _status_equals(state: RunState, params: dict[str, str]) -> tuple[bool, list[str]]:
    """``status_equals`` — the latest envelope from the named agent has the expected status."""
    agent = params.get("agent", "").strip()
    expected = params.get("expected_status", "").strip()
    if not agent or not expected:
        return False, [
            "predicate_kind=status_equals requires params.agent and params.expected_status"
        ]
    matched = [env for env in state.envelopes if env["agent"] == agent]
    if not matched:
        return False, [f"no envelope from agent={agent!r} in this run"]
    actual = matched[-1].get("status")
    if actual != expected:
        return False, [
            f"agent={agent!r}: expected status={expected!r}, got {actual!r}"
        ]
    return True, []


_REGISTRY: dict[PredicateKind, PredicateFn] = {
    PredicateKind.ENVELOPE_PRESENT: _envelope_present,
    PredicateKind.STATUS_EQUALS: _status_equals,
}


def evaluate(
    kind_value: str,
    state: RunState,
    params: dict[str, str],
) -> tuple[bool, list[str]]:
    """Dispatch to the registered evaluator for a ``PredicateKind`` value.

    Raises:
        UnknownPredicate: if ``kind_value`` is not a known PredicateKind
            value, or is known but not evaluated in this block.
    """
    try:
        kind = PredicateKind(kind_value)
    except ValueError as e:
        raise UnknownPredicate(kind_value) from e

    fn = _REGISTRY.get(kind)
    if fn is None:
        raise UnknownPredicate(kind_value)
    return fn(state, params)


def evaluate_required_gate(
    state: RunState, gate_name: str
) -> tuple[bool, list[str]]:
    """Default policy: a gate is held iff some prior phase declared it produced.

    This is the single choke point the dispatcher calls when evaluating
    ``phase.gates_required_before``. Future blocks may extend this function
    to consult a per-gate predicate (e.g. ``no_unsafe_claims`` would re-scan
    envelopes), but the dispatcher itself stays simple.
    """
    if gate_name in state.held_gates:
        return True, []
    return False, [f"gate {gate_name!r} not held by current run state"]


def evaluable_kinds() -> list[str]:
    """Return the list of ``PredicateKind`` values that have an evaluator."""
    return [k.value for k in _REGISTRY]
