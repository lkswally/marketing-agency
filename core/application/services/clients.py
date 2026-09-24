"""Client directory read service (Web Foundation — read-only).

Reusable, application-layer client discovery. Before this module, the
only client-listing capability in the codebase was
``portal/client_discovery.py::discover_clients()`` — a presentation
package helper, not something a future API/Control Center could call
without importing ``portal`` (the wrong dependency direction: the
application layer must not depend on a presentation package).

Deliberately NOT a call into ``portal.client_discovery``, for the same
reason ``core/application/services/approvals.py``'s private
``_discover_client_slugs()`` isn't either — this module supersedes that
private helper's purpose for any FUTURE caller (approvals.py keeps its
own for now; consolidating it is a separate, later cleanup, out of
scope here since it already ships and is tested).

**Cross-tenant by design.** Unlike every other service in this package,
listing clients has no single ``client_slug`` to put in an
:class:`OperationContext` — so, matching the existing precedent set by
:func:`core.application.services.approvals.list_pending`, this takes
``root``/``outputs_root`` directly instead of a context object.

Read-only: no directory is created, no file is touched, nothing is
persisted or audited (there is no "resource" here to audit against).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..result import OperationResult

_RESERVED_DIRS = frozenset({"_shared"})


class ClientSummary(BaseModel):
    """One row of a client directory listing — deliberately minimal:
    just enough for a client picker (``GET /clients``), no raw
    filesystem paths, no internal storage layout exposed."""

    model_config = ConfigDict(frozen=True)

    client_slug: str
    has_memory_data: bool
    """True when a ``<root>/<client_slug>/`` directory exists — i.e.
    the client has at least one persisted entity (intake, strategy
    report, job, approval, ...)."""
    has_outputs: bool
    """True when an ``<outputs_root>/<client_slug>/`` directory exists
    — i.e. at least one artifact (Markdown/JSON report) was written for
    this client."""


def list_clients(
    *, root: Path, outputs_root: Path | None = None,
) -> OperationResult:
    """List every client slug known under ``root`` and/or
    ``outputs_root``, sorted alphabetically.

    A client appears if EITHER location knows about it (same union
    semantics as the portal's own discovery, preserved deliberately —
    see module docstring). Missing roots are tolerated: zero entries,
    never an error.
    """
    memory_slugs = _list_subdirs(root)
    outputs_slugs = _list_subdirs(outputs_root) if outputs_root is not None else set()

    all_slugs = sorted((memory_slugs | outputs_slugs) - _RESERVED_DIRS)
    summaries = [
        ClientSummary(
            client_slug=slug,
            has_memory_data=slug in memory_slugs,
            has_outputs=slug in outputs_slugs,
        )
        for slug in all_slugs
    ]
    return OperationResult.ok_result(data=summaries)


def _list_subdirs(base: Path | str) -> set[str]:
    p = Path(base)
    if not p.exists() or not p.is_dir():
        return set()
    return {
        entry.name for entry in p.iterdir()
        if entry.is_dir() and not entry.name.startswith("_meta")
    }


__all__ = ["ClientSummary", "list_clients"]
