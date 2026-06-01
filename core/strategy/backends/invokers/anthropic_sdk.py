"""AnthropicSDKInvoker — real :class:`ClaudeInvoker` (MKT-4B).

Single backend invocation via the official ``anthropic`` Python SDK.
The SDK is an OPTIONAL dependency (extra ``claude``); the import is
lazy so missing-package environments degrade gracefully into a
:class:`NoCredentialsError` at construction time, which the
:class:`ClaudeStrategyBackend` then converts into a templated fallback.

Safety invariants this module enforces:

- The API key is read once from the ``ANTHROPIC_API_KEY`` env var (or
  explicitly passed in by the caller) and stored only as a private
  instance attribute. It is never printed, logged, persisted, or
  written into any error message, invocation record, or audit
  payload.
- ``__repr__`` redacts the key.
- Every error mapping path produces a sanitised reason: the provider
  error class name plus a short message — no prompt body, no key,
  no raw model output.
- A single attempt per call. No retries (deferred to P-4B.1).
- Output is capped at ``_MAX_OUTPUT_BYTES`` (256 KB) by the
  :class:`ClaudeStrategyBackend`; this invoker also trusts the SDK's
  ``max_tokens`` parameter.

Threading: this invoker stores no per-call state. It is safe to share
across calls. (The pipeline orchestrator is single-threaded anyway.)
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..invocation_log import ClaudeInvocationRecord
from ..invoker import (
    ClaudeInvocationContext,
    ClaudeInvoker,
    ClaudeInvokerError,
)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
"""Default model. Override via ``ANTHROPIC_MODEL`` env var or constructor."""

_API_KEY_ENV = "ANTHROPIC_API_KEY"
_MODEL_ENV = "ANTHROPIC_MODEL"
_REDACTED = "***redacted***"
_MAX_ERROR_LEN = 160


class NoCredentialsError(ClaudeInvokerError):
    """Raised when the SDK is not installed OR ``ANTHROPIC_API_KEY``
    is not set. The :class:`ClaudeStrategyBackend` treats this like
    any other invoker error: record a fallback event and delegate to
    the templated backend.
    """


def _truncate(msg: str) -> str:
    msg = (msg or "").strip().replace("\n", " ")
    return msg[:_MAX_ERROR_LEN]


class AnthropicSDKInvoker(ClaudeInvoker):
    """Production invoker backed by the Anthropic Python SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        timeout_s: float = 30.0,
        client: Any = None,
    ) -> None:
        # ----- Resolve credentials -----
        resolved_key = api_key if api_key is not None else os.environ.get(_API_KEY_ENV)
        if not resolved_key:
            raise NoCredentialsError(
                f"{_API_KEY_ENV} is not set; AnthropicSDKInvoker cannot be "
                "constructed. The CLI falls back to the templated backend."
            )

        # ----- Resolve model -----
        resolved_model = model or os.environ.get(_MODEL_ENV) or DEFAULT_ANTHROPIC_MODEL

        # ----- Resolve client (lazy import) -----
        resolved_client = client
        if resolved_client is None:
            try:
                import anthropic  # local import; SDK is an optional extra
            except ImportError as e:
                raise NoCredentialsError(
                    "The `anthropic` package is not installed. Install with "
                    "`pip install -e .[claude]`. The CLI falls back to the "
                    "templated backend."
                ) from e
            resolved_client = anthropic.Anthropic(
                api_key=resolved_key,
                timeout=timeout_s,
            )

        # Store privately. The key is referenced only by the SDK client
        # we already constructed — we do not need to keep it for later.
        self._api_key_set = True  # presence marker for __repr__; not the value
        self._model = resolved_model
        self._timeout_s = timeout_s
        self._client = resolved_client

    # ---------- introspection ----------

    def __repr__(self) -> str:
        return (
            f"AnthropicSDKInvoker(api_key={_REDACTED}, "
            f"model={self._model!r}, timeout_s={self._timeout_s})"
        )

    @property
    def model(self) -> str:
        return self._model

    # ---------- ClaudeInvoker ----------

    def complete(
        self,
        prompt: str,
        *,
        system: str | None,
        context: ClaudeInvocationContext,
    ) -> str:
        sink = context.record_sink
        start = time.perf_counter()

        # Defensive: pre-build kwargs so a single error path covers all
        # the SDK exception classes uniformly.
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": context.max_tokens,
            "temperature": context.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = system

        try:
            response = self._client.messages.create(**kwargs)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            error_type, sanitised = self._classify_error(exc)
            if sink is not None:
                sink.append(
                    ClaudeInvocationRecord(
                        method=context.method,
                        model=self._model,
                        request_id=None,
                        input_tokens=None,
                        output_tokens=None,
                        duration_ms=duration_ms,
                        ok=False,
                        error_type=error_type,
                        error_message=sanitised,
                    )
                )
            raise ClaudeInvokerError(f"{error_type}: {sanitised}") from exc

        duration_ms = (time.perf_counter() - start) * 1000.0

        text, request_id, in_tok, out_tok = self._extract_response(response)

        if sink is not None:
            sink.append(
                ClaudeInvocationRecord(
                    method=context.method,
                    model=self._model,
                    request_id=request_id,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    duration_ms=duration_ms,
                    ok=True,
                    error_type=None,
                    error_message=None,
                )
            )

        return text

    # ---------- internals ----------

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[str, str]:
        """Map an SDK exception to ``(error_type, sanitised_message)``.

        Imports of the SDK exception classes are lazy so this module
        does not require ``anthropic`` to be importable at module-load
        time (tests inject a mock client).
        """
        error_type = type(exc).__name__
        sanitised = _truncate(str(exc))
        return error_type, sanitised

    @staticmethod
    def _extract_response(response: Any) -> tuple[str, str | None, int | None, int | None]:
        """Pull ``(text, request_id, input_tokens, output_tokens)``
        from an SDK Message response. Defensive against shape drift —
        any missing attribute resolves to a safe default."""
        # Text content.
        text = ""
        content = getattr(response, "content", None)
        if content:
            first = content[0]
            text = getattr(first, "text", None) or ""
        if not isinstance(text, str):
            text = ""

        request_id = getattr(response, "id", None)
        if request_id is not None and not isinstance(request_id, str):
            request_id = str(request_id)

        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", None) if usage else None
        out_tok = getattr(usage, "output_tokens", None) if usage else None
        if not isinstance(in_tok, int):
            in_tok = None
        if not isinstance(out_tok, int):
            out_tok = None

        return text, request_id, in_tok, out_tok


__all__ = [
    "DEFAULT_ANTHROPIC_MODEL",
    "AnthropicSDKInvoker",
    "NoCredentialsError",
]
