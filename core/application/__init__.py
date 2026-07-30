"""Application service layer (MKT-11A).

The stable boundary between input adapters (CLI today; a future FastAPI
service, Next.js Control Center, and MCP tools) and the domain
(``core/<domain>/``), memory (``core/memory/``) and audit layers.

**Rules, enforced by tests, not just convention:**

- Adapters call only what is re-exported here (or from
  ``core.application.services``) — never a domain builder, never
  ``core.memory`` directly.
- Every service function takes an :class:`~core.application.context.OperationContext`
  and returns an :class:`~core.application.result.OperationResult`. No
  domain exception crosses this boundary.
- No business logic lives here — a service function orchestrates
  (load → call domain → persist → write artifacts → build result); it
  does not decide marketing/SEO/approval rules itself.

This milestone (MKT-11A) intentionally covers three services only:
SEO Intelligence Report, Analytics snapshot reads, and Approvals. See
``docs/MKT-11A-Application-Services-Inventory.md`` for what is deferred.
"""

from __future__ import annotations

from .artifacts import ArtifactWriteError, OutputLayout
from .context import (
    DEFAULT_DATA_ROOT,
    DEFAULT_OUTPUTS_ROOT,
    OperationContext,
    OperationRole,
    OperationSource,
)
from .result import (
    Artifact,
    ErrorCode,
    OperationError,
    OperationResult,
    OperationStatus,
    OperationWarning,
)

__all__ = [
    "DEFAULT_DATA_ROOT",
    "DEFAULT_OUTPUTS_ROOT",
    "Artifact",
    "ArtifactWriteError",
    "ErrorCode",
    "OperationContext",
    "OperationError",
    "OperationResult",
    "OperationRole",
    "OperationSource",
    "OperationStatus",
    "OperationWarning",
    "OutputLayout",
]
