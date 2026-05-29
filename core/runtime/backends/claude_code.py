"""ClaudeCodeBackend — scaffolding only. NOT IMPLEMENTED.

A future block will implement this backend by spawning a Claude Code
subagent (via the ``Agent`` tool) for each invocation. Until then, every
method raises :class:`NotImplementedError` with a pointer to the safety
documentation that must be reviewed first.

This module deliberately does NOT import any Anthropic SDK or Claude CLI
client. Its existence lets downstream code be written against
:class:`AgentBackend` today without depending on a backend that does not
exist yet.

Promotion checklist lives in ``docs/runtime/agent-backend-safety.md``.
"""

from __future__ import annotations

from typing import Any

from core.contracts import ReturnEnvelope

from ..backend import AgentBackend, AgentInvocation

_NOT_IMPLEMENTED_MSG = (
    "ClaudeCodeBackend is scaffolding only — the real Claude Code subagent "
    "spawn backend is not implemented yet. The safety boundaries that MUST "
    "be in place before promotion are documented in "
    "docs/runtime/agent-backend-safety.md. Use MockAgentBackend for now."
)


class ClaudeCodeBackend(AgentBackend):
    """Future Claude-Code-backed :class:`AgentBackend`. Not callable today."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept any constructor args silently so callers can be wired in
        # advance; we only fail when someone actually tries to invoke ``run``.
        self._args = args
        self._kwargs = kwargs

    def run(self, invocation: AgentInvocation) -> ReturnEnvelope:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
