"""MockAgentBackend — default backend (MKT-2A → MKT-2B).

Produces deterministic, side-effect-free envelopes. Lives in the runtime
package so future code paths can swap to a real backend without test churn.
"""

from __future__ import annotations

from core.contracts import (
    ArtifactKind,
    ArtifactRef,
    EnvelopeStatus,
    ReturnEnvelope,
)
from core.domain.base import utcnow

from ..backend import AgentBackend, AgentInvocation


class MockAgentBackend(AgentBackend):
    """Returns a minimal valid envelope for any invocation."""

    def run(self, invocation: AgentInvocation) -> ReturnEnvelope:
        return ReturnEnvelope(
            status=EnvelopeStatus.COMPLETADO,
            agent=invocation.agent_id,
            task=f"[mock] {invocation.workflow_id}.{invocation.phase_id}",
            client_slug=invocation.client_slug,
            artifacts=[
                ArtifactRef(
                    path=f"mock://{invocation.agent_id}/{invocation.phase_id}",
                    kind=ArtifactKind.INLINE,
                    description=(
                        f"mock output from {invocation.agent_id} during "
                        f"{invocation.workflow_id}.{invocation.phase_id}"
                    ),
                )
            ],
            memory_writes=[],
            bloqueadores=[],
            notes=(
                f"Mock envelope. agent={invocation.agent_id} "
                f"phase={invocation.phase_id} workflow={invocation.workflow_id}."
            ),
            produced_at=utcnow(),
        )
