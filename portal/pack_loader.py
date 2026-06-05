"""Safe pack loader for the portal (MKT-9A).

Wraps :class:`core.memory.JsonFileMemory` so a missing pack does
not crash the portal — instead the loader returns a
:class:`PackLoadResult` with ``status=MISSING``. Errors during
deserialisation (malformed JSON, schema drift) are also captured
into ``status=ERROR`` with the exception text, so the operator
sees what happened without the portal dying.

Read-only: no write, no creation. The loader opens files in
read mode only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.memory import EntityNotFound, JsonFileMemory

from .pack_registry import PortalPackSpec


class PackStatus(StrEnum):
    """High-level status the portal surfaces per pack."""

    OK = "ok"
    """Pack exists and loaded cleanly."""

    BLOCKED = "blocked"
    """Pack exists, loaded cleanly, and its posture flag indicates
    publish is blocked."""

    MISSING = "missing"
    """Pack does not exist on disk — informational for optional
    packs, blocker for required packs."""

    ERROR = "error"
    """Pack exists but failed to deserialise — operator must
    inspect the file directly."""


@dataclass(frozen=True)
class PackLoadResult:
    """Outcome of loading one pack."""

    spec: PortalPackSpec
    status: PackStatus
    data: dict | None
    """Raw JSON dict when ``status`` is ``OK`` / ``BLOCKED`` /
    ``ERROR`` (best-effort partial); ``None`` when ``MISSING``."""

    markdown_path: Path | None
    """Path to the rendered Markdown if one of the known filenames
    exists under ``outputs/<slug>/``; ``None`` otherwise."""

    file_path: Path | None
    """On-disk path to the JSON file when discoverable, ``None``
    otherwise. Useful for the operator to open in their editor."""

    error_message: str | None = None
    """Populated when ``status == ERROR``."""


def load_pack(
    *,
    root: Path | str,
    outputs_dir: Path | str | None,
    client_slug: str,
    spec: PortalPackSpec,
) -> PackLoadResult:
    """Load one pack by registry spec, never raise."""

    memory = JsonFileMemory(Path(root))
    file_path = _entity_file_path(root, client_slug, spec)
    md_path = _find_markdown(outputs_dir, client_slug, spec)
    try:
        data = memory.get(client_slug, spec.kind, spec.singleton_id)
    except EntityNotFound:
        return PackLoadResult(
            spec=spec, status=PackStatus.MISSING,
            data=None, markdown_path=md_path, file_path=None,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the portal
        return PackLoadResult(
            spec=spec, status=PackStatus.ERROR,
            data=None, markdown_path=md_path, file_path=file_path,
            error_message=f"{type(exc).__name__}: {exc}",
        )
    status = PackStatus.OK
    if spec.blocks_publish_field and bool(data.get(spec.blocks_publish_field)):
        status = PackStatus.BLOCKED
    return PackLoadResult(
        spec=spec, status=status,
        data=data, markdown_path=md_path, file_path=file_path,
    )


def load_pack_markdown(path: Path) -> str:
    """Read a Markdown file as text. Returns empty string when the
    file does not exist (defensive)."""

    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


# ---------- helpers ----------


def _entity_file_path(
    root: Path | str, client_slug: str, spec: PortalPackSpec,
) -> Path:
    """Mirror the JsonFileMemory layout to expose the file path
    even when the pack is MISSING (useful in the UI breadcrumb)."""
    return (
        Path(root) / client_slug / spec.kind / f"{spec.singleton_id}.json"
    )


def _find_markdown(
    outputs_dir: Path | str | None,
    client_slug: str,
    spec: PortalPackSpec,
) -> Path | None:
    if outputs_dir is None:
        return None
    base = Path(outputs_dir) / client_slug
    for name in spec.markdown_filenames:
        candidate = base / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


__all__ = ["PackLoadResult", "PackStatus", "load_pack", "load_pack_markdown"]
