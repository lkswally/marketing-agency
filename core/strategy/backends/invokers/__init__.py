"""Real ClaudeInvoker implementations (MKT-4B).

The only one shipped today is :class:`AnthropicSDKInvoker`, which
talks to the Anthropic API via the official Python SDK. The SDK is
declared as an OPTIONAL dependency in ``pyproject.toml`` under the
``claude`` extra — install with::

    pip install -e .[claude]

If the SDK is not installed, importing :mod:`anthropic_sdk` still
succeeds (the import of the ``anthropic`` package is lazy), but
constructing an :class:`AnthropicSDKInvoker` raises
:class:`NoCredentialsError` so the caller can fall back to the
templated backend cleanly.
"""

from __future__ import annotations

from .anthropic_sdk import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicSDKInvoker,
    NoCredentialsError,
)

__all__ = [
    "DEFAULT_ANTHROPIC_MODEL",
    "AnthropicSDKInvoker",
    "NoCredentialsError",
]
