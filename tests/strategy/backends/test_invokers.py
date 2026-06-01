"""Invoker semantics for MKT-4A."""

from __future__ import annotations

import pytest

from core.strategy.backends.invoker import (
    ClaudeInvocationContext,
    ClaudeInvokerError,
    NoRealInvokerError,
    RefusingClaudeInvoker,
    ScriptedClaudeInvoker,
)


def _ctx(method: str = "value_proposition") -> ClaudeInvocationContext:
    return ClaudeInvocationContext(method=method, client_slug="acme")


# ---------- ScriptedClaudeInvoker ----------


def test_scripted_returns_canned_response_per_method() -> None:
    inv = ScriptedClaudeInvoker(responses={"value_proposition": "{\"x\":1}"})
    out = inv.complete("hi", system=None, context=_ctx("value_proposition"))
    assert out == '{"x":1}'


def test_scripted_records_calls() -> None:
    inv = ScriptedClaudeInvoker(responses={"value_proposition": "{}"})
    inv.complete("PROMPT", system="SYS", context=_ctx("value_proposition"))
    assert inv.calls == [("value_proposition", "PROMPT")]


def test_scripted_raises_when_method_unknown() -> None:
    inv = ScriptedClaudeInvoker(responses={})
    with pytest.raises(ClaudeInvokerError):
        inv.complete("p", system=None, context=_ctx("anything"))


# ---------- RefusingClaudeInvoker ----------


def test_refusing_always_raises_no_real_invoker_error() -> None:
    inv = RefusingClaudeInvoker()
    with pytest.raises(NoRealInvokerError):
        inv.complete("p", system=None, context=_ctx())


def test_refusing_error_message_mentions_mkt_4b() -> None:
    inv = RefusingClaudeInvoker()
    with pytest.raises(NoRealInvokerError) as ei:
        inv.complete("p", system=None, context=_ctx())
    assert "MKT-4" in str(ei.value)


def test_no_real_invoker_error_is_a_claude_invoker_error() -> None:
    assert issubclass(NoRealInvokerError, ClaudeInvokerError)
