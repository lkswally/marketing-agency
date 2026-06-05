"""Discover clients with persisted artifacts (MKT-9A).

The portal lists clients by scanning two locations:

1. The ``JsonFileMemory`` root (e.g. ``data/``) — every direct
   subdirectory that is not the reserved ``_shared`` slug is a
   client.
2. The outputs directory (e.g. ``outputs/``) — every direct
   subdirectory is a client.

A client appears in the portal if **either** location knows
about it. The union is sorted alphabetically for stable UI.

Read-only: no directory is created, no file is touched.
"""

from __future__ import annotations

from pathlib import Path

_RESERVED_DIRS = frozenset({"_shared"})


def discover_clients(
    *,
    root: Path | str,
    outputs_dir: Path | str | None,
) -> list[str]:
    """Return the sorted unique list of client slugs the portal
    can show. Missing roots are tolerated — they contribute zero
    entries instead of raising."""

    slugs: set[str] = set()
    slugs.update(_list_subdirs(root))
    if outputs_dir is not None:
        slugs.update(_list_subdirs(outputs_dir))
    return sorted(s for s in slugs if s not in _RESERVED_DIRS)


def list_outputs_files(
    *, outputs_dir: Path | str, client_slug: str,
) -> list[Path]:
    """Return every ``*.md`` and ``*.json`` file under
    ``outputs/<slug>/``. Returns ``[]`` when the directory does
    not exist. Sorted by path for deterministic display."""

    base = Path(outputs_dir) / client_slug
    if not base.exists() or not base.is_dir():
        return []
    out: list[Path] = []
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in (".md", ".json"):
            out.append(path)
    return sorted(out)


def _list_subdirs(base: Path | str) -> list[str]:
    p = Path(base)
    if not p.exists() or not p.is_dir():
        return []
    out: list[str] = []
    for entry in p.iterdir():
        if entry.is_dir() and not entry.name.startswith("_meta"):
            out.append(entry.name)
    return out


__all__ = ["discover_clients", "list_outputs_files"]
