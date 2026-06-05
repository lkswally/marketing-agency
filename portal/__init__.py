"""Portal MVP (MKT-9A).

Read-only Streamlit portal for browsing the packs MARKETING-AGENCY-OS
produces. Pure file reads + ``JsonFileMemory`` reads — no writes,
no API calls, no Streamlit-side mutation.

The Streamlit entry point is :mod:`portal.app`. Everything else in
this package is plain Python (no streamlit dependency) so it is
fully unit-testable in CI.
"""

from __future__ import annotations

from .checklist import (
    ChecklistResult,
    PreflightChecklist,
    build_preflight_checklist,
)
from .client_discovery import discover_clients, list_outputs_files
from .pack_loader import (
    PackLoadResult,
    PackStatus,
    load_pack,
    load_pack_markdown,
)
from .pack_registry import (
    PORTAL_PACK_REGISTRY,
    PortalPackSpec,
    iter_pack_specs,
)

__all__ = [
    "ChecklistResult",
    "PORTAL_PACK_REGISTRY",
    "PackLoadResult",
    "PackStatus",
    "PortalPackSpec",
    "PreflightChecklist",
    "build_preflight_checklist",
    "discover_clients",
    "iter_pack_specs",
    "list_outputs_files",
    "load_pack",
    "load_pack_markdown",
]
