"""ClaudeInvocationRecord — per-call invocation metadata (MKT-4B).

Recorded once per call to a :class:`ClaudeInvoker` that supports the
``record_sink`` channel in :class:`ClaudeInvocationContext`. The
:class:`AnthropicSDKInvoker` (MKT-4B) populates one record per call,
both on success (``ok=True``, with model + request_id + token counts)
and on failure (``ok=False``, with ``error_type`` + sanitised
``error_message``).

The model is deliberately small. It NEVER contains:

- The API key.
- The prompt body or the system message.
- The raw model output.
- The tenant intake or any business data.

Only safe traceability metadata: model id, request id, token counts,
duration, ok flag, sanitised error name and message.
"""

from __future__ import annotations

from pydantic import Field

from core.domain.base import DomainModel

_MAX_ERROR_LEN = 160


class ClaudeInvocationRecord(DomainModel):
    """One LLM call attempt — successful or failed."""

    method: str = Field(min_length=1, max_length=64)
    """The :class:`StrategyBackend` method, e.g. ``"value_proposition"``."""

    model: str | None = Field(default=None, max_length=120)
    """The model id returned by the provider (or the configured target
    when the call failed before reaching the wire)."""

    request_id: str | None = Field(default=None, max_length=120)
    """Provider-assigned request id, ``None`` on failure paths."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)

    duration_ms: float = Field(ge=0.0)
    """Wall-clock duration measured around the provider call. Includes
    the time spent inside the SDK; excludes prompt building and
    Pydantic validation."""

    ok: bool
    """``True`` if the call succeeded AND returned a non-empty string.
    ``False`` for every failure path (auth, rate-limit, timeout, connection,
    generic API error, oversized output)."""

    error_type: str | None = Field(default=None, max_length=80)
    """Short class name of the provider error, e.g.
    ``"AuthenticationError"``. ``None`` on success."""

    error_message: str | None = Field(default=None, max_length=_MAX_ERROR_LEN)
    """Sanitised error message. Truncated to ``_MAX_ERROR_LEN`` chars,
    stripped of API key and prompt content by the invoker before
    appending to the record."""


__all__ = ["ClaudeInvocationRecord"]
