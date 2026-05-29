"""MockAgent — deterministic, side-effect-free producer of valid envelopes.

The MockAgent exists so the MKT-2A dispatcher can be exercised end-to-end
without any Claude Code spawn or external service. Promotion to a real
Claude-Code-backed agent runtime is a separate block (MKT-2B+).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts import (
    ArtifactKind,
    ArtifactRef,
    EnvelopeStatus,
    ReturnEnvelope,
)
from core.domain.base import utcnow


@dataclass(frozen=True)
class MockAgentInput:
    """Everything a MockAgent needs to produce a deterministic envelope."""

    agent_id: str
    phase_id: str
    workflow_id: str
    client_slug: str


class MockAgent:
    """Produces a valid :class:`ReturnEnvelope` for any agent / phase pair.

    The envelope is intentionally minimal:
    - status: completado
    - one inline artifact pointing at a ``mock://`` URI
    - no memory_writes, no claims_audit
    - notes describing the mock origin

    Callers that need a richer mock (e.g. emitting claim audits) should
    subclass and override :meth:`run`.
    """

    def run(self, input_: MockAgentInput) -> ReturnEnvelope:
        return ReturnEnvelope(
            status=EnvelopeStatus.COMPLETADO,
            agent=input_.agent_id,
            task=f"[mock] {input_.workflow_id}.{input_.phase_id}",
            client_slug=input_.client_slug,
            artifacts=[
                ArtifactRef(
                    path=f"mock://{input_.agent_id}/{input_.phase_id}",
                    kind=ArtifactKind.INLINE,
                    description=(
                        f"mock output from {input_.agent_id} during "
                        f"{input_.workflow_id}.{input_.phase_id}"
                    ),
                )
            ],
            memory_writes=[],
            bloqueadores=[],
            notes=(
                f"Mock envelope. agent={input_.agent_id} "
                f"phase={input_.phase_id} workflow={input_.workflow_id}."
            ),
            produced_at=utcnow(),
        )
