"""Strategy content backends (MKT-4A).

This package adds a swappable content-generation layer on top of the
deterministic ``core.strategy.templates`` functions. The W7 workflow
agent backend (``core.strategy.backend.W7TemplatedAgentBackend``)
delegates the *creative* content stages (positioning, campaign,
copies, emails, reels, creative brief) to whichever
:class:`StrategyBackend` is wired in.

In MKT-4A the only two implementations are:

- :class:`TemplatedStrategyBackend` — pure wrapper over
  ``core.strategy.templates``. Always succeeds. The safe default.
- :class:`ClaudeStrategyBackend` — uses prompts + a pluggable
  :class:`ClaudeInvoker` + Pydantic validation, with automatic
  fallback to a templated backend on any error.

The actual call to a real Claude LLM is delegated to a
:class:`ClaudeInvoker`. **No real invoker is wired in this block**
— the only invokers provided are :class:`ScriptedClaudeInvoker`
(for tests) and :class:`RefusingClaudeInvoker` (safe default that
always raises). Wiring a real invoker (Anthropic SDK or
``claude`` CLI subprocess) is the scope of MKT-4B.
"""

from __future__ import annotations

from .base import (
    BACKEND_DEFAULT,
    BackendFallbackEvent,
    BackendKind,
    StrategyBackend,
    StrategyBackendError,
)
from .claude import (
    ClaudeOutputInvalid,
    ClaudeStrategyBackend,
)
from .invocation_log import ClaudeInvocationRecord
from .invoker import (
    ClaudeInvocationContext,
    ClaudeInvoker,
    ClaudeInvokerError,
    NoRealInvokerError,
    RefusingClaudeInvoker,
    ScriptedClaudeInvoker,
)
from .invokers import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicSDKInvoker,
    NoCredentialsError,
)
from .templated import TemplatedStrategyBackend

__all__ = [
    "BACKEND_DEFAULT",
    "DEFAULT_ANTHROPIC_MODEL",
    "AnthropicSDKInvoker",
    "BackendFallbackEvent",
    "BackendKind",
    "ClaudeInvocationContext",
    "ClaudeInvocationRecord",
    "ClaudeInvoker",
    "ClaudeInvokerError",
    "ClaudeOutputInvalid",
    "ClaudeStrategyBackend",
    "NoCredentialsError",
    "NoRealInvokerError",
    "RefusingClaudeInvoker",
    "ScriptedClaudeInvoker",
    "StrategyBackend",
    "StrategyBackendError",
    "TemplatedStrategyBackend",
]
