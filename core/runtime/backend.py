"""Agent backend interface.

Every agent backend (mock today, Claude Code subagent spawn tomorrow,
Anthropic SDK call after that) implements this single abstract surface so
the dispatcher does not care which one is wired in.

The dispatcher injects a backend via ``MinimalDispatcher(memory, agent_backend=...)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.contracts import ReturnEnvelope


@dataclass(frozen=True)
class AgentInvocation:
    """Everything an :class:`AgentBackend` needs to produce an envelope.

    Kept intentionally small in ``v1``. Future blocks add:
    - ``agent_spec``: a frozen view of the agent's AgentSpec.
    - ``memory_ro``: a read-only view of the client's memory.
    - ``inputs``: a typed dict of resolved upstream entities.
    """

    agent_id: str
    phase_id: str
    workflow_id: str
    client_slug: str


class AgentBackend(ABC):
    """Abstract executor of a single agent for a single phase."""

    @abstractmethod
    def run(self, invocation: AgentInvocation) -> ReturnEnvelope:
        """Produce a :class:`ReturnEnvelope` for the given invocation.

        Implementations MUST return a fully-formed, valid envelope. The
        dispatcher re-validates it strictly before persisting.
        """
