"""ClaudeInvoker ABC and the only two invokers shipped in MKT-4A.

The invoker is the one and only point at which a real LLM call would
happen. In MKT-4A **no real invoker exists**:

- :class:`ScriptedClaudeInvoker` returns predetermined strings keyed
  by ``method``. Used in tests and by anyone who wants to feed canned
  responses for local exploration.
- :class:`RefusingClaudeInvoker` always raises
  :class:`NoRealInvokerError`. This is the safe default the CLI wires
  in when the operator passes ``--backend claude``: every call fails
  fast, the ClaudeStrategyBackend falls back to templated, and the
  fact is surfaced in the audit trail, the run summary and stderr.

A real :class:`ClaudeInvoker` (Anthropic SDK, ``claude`` CLI
subprocess, AWS Bedrock, etc.) is the explicit scope of **MKT-4B**.
This module deliberately imports no SDK and opens no socket.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ClaudeInvokerError(RuntimeError):  # noqa: N818
    """Base class for invoker-level errors. The ClaudeStrategyBackend
    catches every subclass and falls back to templated."""


class NoRealInvokerError(ClaudeInvokerError):
    """Raised by :class:`RefusingClaudeInvoker`. Indicates that the
    operator asked for ``--backend claude`` but no real invoker has
    been wired yet (MKT-4B scope)."""


@dataclass(frozen=True)
class ClaudeInvocationContext:
    """Everything an invoker is allowed to know about the call.

    Notice what is **not** here: filesystem paths, environment
    variables, credentials, network endpoints. The invoker receives
    only the prompt, an optional system message, and a short
    identifier of which strategy method is being generated. The
    backend remains responsible for serialization, validation, and
    fallback.
    """

    method: str
    """Which StrategyBackend method, e.g. ``"value_proposition"``."""

    client_slug: str
    """The tenant slug. Useful for the invoker to scope a per-tenant
    rate limit or audit log, but the invoker MUST NOT read or write
    anything for any other tenant."""

    max_tokens: int = 2048
    temperature: float = 0.7

    record_sink: list | None = None
    """Optional list to receive a :class:`ClaudeInvocationRecord` for
    each call. Real invokers (MKT-4B's :class:`AnthropicSDKInvoker`)
    append exactly one record per call — both on success and on
    failure (with ``ok=False``). The two MKT-4A invokers
    (:class:`ScriptedClaudeInvoker`, :class:`RefusingClaudeInvoker`)
    ignore this field. Backends that care about traceability create
    a fresh empty list per call and drain it after."""


class ClaudeInvoker(ABC):
    """Single-method interface. Returns the raw model output as text.

    Implementations:

    - MUST NOT raise except via subclasses of :class:`ClaudeInvokerError`.
    - MUST NOT exceed ``context.max_tokens``.
    - MUST NOT block longer than a reasonable per-call timeout (the
      backend doesn't enforce one in v1, but a real invoker should).
    - MUST NOT touch the filesystem outside the tenant scope.
    - MUST NOT make outbound network calls to anything other than the
      single declared LLM endpoint (none in MKT-4A — no invoker is
      wired).
    """

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None,
        context: ClaudeInvocationContext,
    ) -> str: ...


# ---------- shipped invokers (MKT-4A) ----------


@dataclass
class ScriptedClaudeInvoker(ClaudeInvoker):
    """Returns a canned string per ``method``. Test-friendly.

    Construct with a mapping ``method → response``. Unknown methods
    raise :class:`ClaudeInvokerError` (the backend treats this as a
    fallback signal, exactly the same as a real invoker that errors
    out).
    """

    responses: dict[str, str] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list, init=False, repr=False)
    """Call log: list of ``(method, prompt)`` tuples. Useful in tests."""

    def complete(
        self,
        prompt: str,
        *,
        system: str | None,
        context: ClaudeInvocationContext,
    ) -> str:
        self.calls.append((context.method, prompt))
        if context.method not in self.responses:
            raise ClaudeInvokerError(
                f"ScriptedClaudeInvoker has no canned response for "
                f"method {context.method!r}"
            )
        return self.responses[context.method]


class RefusingClaudeInvoker(ClaudeInvoker):
    """Safe default. Always raises :class:`NoRealInvokerError`.

    Wired by the CLI when ``--backend claude`` is requested. Each
    call to ``complete`` fails fast, the ClaudeStrategyBackend
    records a fallback event, and the templated backend produces
    the actual content. The audit trail and run summary make it
    explicit that no real Claude call happened.
    """

    def complete(
        self,
        prompt: str,
        *,
        system: str | None,
        context: ClaudeInvocationContext,
    ) -> str:
        raise NoRealInvokerError(
            "No real Claude invoker is wired. Calls fall back to the templated "
            "backend. Set ANTHROPIC_API_KEY and pass --backend claude to use "
            "AnthropicSDKInvoker."
        )


__all__ = [
    "ClaudeInvocationContext",
    "ClaudeInvoker",
    "ClaudeInvokerError",
    "NoRealInvokerError",
    "RefusingClaudeInvoker",
    "ScriptedClaudeInvoker",
]
