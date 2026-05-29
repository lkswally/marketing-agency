"""Agent specs — Pydantic contract ``agent-spec.v1`` + loader."""

from __future__ import annotations

from .loader import (
    DEFAULT_AGENTS_DIR,
    AgentLoadError,
    load_agent,
    load_all_agents,
)
from .spec import AGENT_SPEC_VERSION, AgentIOEntry, AgentSpec

__all__ = [
    "AGENT_SPEC_VERSION",
    "AgentSpec",
    "AgentIOEntry",
    "load_agent",
    "load_all_agents",
    "AgentLoadError",
    "DEFAULT_AGENTS_DIR",
]
