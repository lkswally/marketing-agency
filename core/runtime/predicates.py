"""Predicate evaluators for phase-gate kinds.

MKT-2A only evaluates ``envelope_present``. Every other ``PredicateKind``
raises :class:`UnknownPredicate` — explicitly, so the dispatcher fails
loud when a workflow asks for something this block does not implement.
"""

from __future__ import annotations

from collections.abc import Callable

from core.contracts import PredicateKind

from .errors import UnknownPredicate

# A predicate evaluator returns (passed, blockers).
# - passed: True iff the predicate holds for the current run state.
# - blockers: human-readable reasons when ``passed`` is False.
PredicateFn = Callable[["RunState", dict[str, str]], tuple[bool, list[str]]]


def _envelope_present(state: RunState, params: dict[str, str]) -> tuple[bool, list[str]]:
    """``envelope_present`` — the named agent has produced an envelope in this run."""
    agent = params.get("agent", "").strip()
    if not agent:
        return False, ["predicate_kind=envelope_present requires params.agent"]
    matched = [env for env in state.envelopes if env["agent"] == agent]
    if not matched:
        return False, [f"no envelope from agent={agent!r} in this run"]
    return True, []


_REGISTRY: dict[PredicateKind, PredicateFn] = {
    PredicateKind.ENVELOPE_PRESENT: _envelope_present,
}


def evaluate(
    kind_value: str,
    state: RunState,
    params: dict[str, str],
) -> tuple[bool, list[str]]:
    """Dispatch to the registered evaluator.

    Raises:
        UnknownPredicate: if ``kind_value`` is not a known PredicateKind
            value, or is known but not evaluated in MKT-2A.
    """
    try:
        kind = PredicateKind(kind_value)
    except ValueError as e:
        raise UnknownPredicate(kind_value) from e

    fn = _REGISTRY.get(kind)
    if fn is None:
        raise UnknownPredicate(kind_value)
    return fn(state, params)


# Public helper for the dispatcher: list of evaluable predicate kinds.
def evaluable_kinds() -> list[str]:
    return [k.value for k in _REGISTRY]


# Forward-ref placeholder for typing; the real ``RunState`` lives in dispatcher.
class RunState:  # pragma: no cover - structural placeholder
    envelopes: list[dict]
    held_gates: set[str]
