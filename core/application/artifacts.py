"""Centralized artifact writer (MKT-11A).

Collapses the write-side of the CLI's canonical duplicated block
(`docs/MKT-11A-Application-Services-Inventory.md` §1) into one function:

```python
outputs_dir.mkdir(parents=True, exist_ok=True)
md_path.write_text(render_markdown_x(pack), encoding="utf-8")
json_path.write_text(pack.to_json(indent=2), encoding="utf-8")
```

**Layout is explicit, never inferred** — the inventory found two
incompatible conventions in the existing CLI (flat vs. per-client
subdirectory). Silently unifying them would be a behaviour change, which
is out of scope for MKT-11A (tracked as D-11A.1). Callers state which
layout they want; the writer reproduces exactly what the equivalent
inline code did.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from .result import Artifact, ErrorCode, OperationError


class OutputLayout(StrEnum):
    """Where artifacts land relative to the outputs root."""

    FLAT = "flat"
    """``<outputs_root>/<filename>`` — e.g. ``seo-report``, ``ads-analyze``."""

    PER_CLIENT = "per_client"
    """``<outputs_root>/<client_slug>/<filename>`` — e.g. ``intake``,
    ``run-campaign``."""


class ArtifactWriteError(Exception):
    """Raised only for programming errors (e.g. an empty filename).
    Policy failures (path escape, overwrite conflict) are returned as
    :class:`OperationError`, never raised — see :func:`write_artifacts`."""


def resolve_output_dir(
    *, outputs_root: Path, client_slug: str, layout: OutputLayout,
) -> Path:
    """Resolve the directory artifacts are written into, per layout."""
    if layout is OutputLayout.PER_CLIENT:
        return outputs_root / client_slug
    return outputs_root


def check_path_allowed(*, path: Path, outputs_root: Path) -> bool:
    """True when ``path`` resolves inside ``outputs_root`` — guards
    against a caller-supplied ``--outputs-dir`` (or an artifact filename)
    that escapes the permitted root (e.g. ``../../etc``)."""
    root_resolved = outputs_root.resolve()
    try:
        path.resolve().relative_to(root_resolved)
    except ValueError:
        return False
    return True


def write_artifacts(
    *,
    outputs_root: Path,
    client_slug: str,
    layout: OutputLayout,
    files: dict[str, str],
    overwrite: bool,
    dry_run: bool,
) -> tuple[list[Artifact], OperationError | None]:
    """Write ``files`` (filename → content) to the resolved output dir.

    Returns ``(artifacts, None)`` on success, or ``([], error)`` when the
    resolved directory escapes ``outputs_root`` or an existing file blocks
    a non-overwrite write. Never raises for policy failures — only
    :class:`ArtifactWriteError` for programmer error (empty ``files``
    filename).

    In dry-run mode, no directory is created and no file is written; the
    returned artifacts carry ``would_write=True`` at the paths that WOULD
    be produced.
    """
    if any(not name for name in files):
        raise ArtifactWriteError("artifact filename must be non-empty")

    out_dir = resolve_output_dir(
        outputs_root=outputs_root, client_slug=client_slug, layout=layout,
    )
    paths = {name: out_dir / name for name in files}

    for path in paths.values():
        if not check_path_allowed(path=path, outputs_root=outputs_root):
            return [], OperationError(
                code=ErrorCode.PATH_NOT_ALLOWED,
                message=f"resolved artifact path escapes the permitted output root: {path}",
            )

    if dry_run:
        return [
            Artifact(path=path, kind=_kind_for(name), would_write=True)
            for name, path in paths.items()
        ], None

    if not overwrite:
        existing = [p for p in paths.values() if p.exists()]
        if existing:
            listing = ", ".join(str(p) for p in existing)
            return [], OperationError(
                code=ErrorCode.ALREADY_EXISTS,
                message=f"output already exists: {listing}",
                remediation="pass overwrite=True to replace it",
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Artifact] = []
    for name, content in files.items():
        path = paths[name]
        path.write_text(content, encoding="utf-8")
        artifacts.append(Artifact(path=path, kind=_kind_for(name)))
    return artifacts, None


def _kind_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".json":
        return "json"
    return suffix.lstrip(".") or "file"


__all__ = [
    "ArtifactWriteError",
    "OutputLayout",
    "check_path_allowed",
    "resolve_output_dir",
    "write_artifacts",
]
