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
    """Load one pack by registry spec, never raise.

    MKT-9B: when ``spec.extra_singleton_ids`` is non-empty, the
    loader probes the primary singleton first, then each extra
    singleton. The aggregate status is BLOCKED if ANY loaded
    payload has a truthy ``blocks_publish_field``; otherwise OK
    if any singleton loaded; otherwise MISSING.
    """

    memory = JsonFileMemory(Path(root))
    md_path = _find_markdown(outputs_dir, client_slug, spec)

    singletons = (spec.singleton_id, *spec.extra_singleton_ids)
    primary_data: dict | None = None
    primary_file_path = _entity_file_path(
        root, client_slug, spec.kind, spec.singleton_id,
    )
    any_loaded = False
    any_blocked = False
    last_error: str | None = None

    for sid in singletons:
        try:
            data = memory.get(client_slug, spec.kind, sid)
        except EntityNotFound:
            continue
        except Exception as exc:  # noqa: BLE001 — never crash the portal
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        any_loaded = True
        if primary_data is None:
            primary_data = data
            primary_file_path = _entity_file_path(
                root, client_slug, spec.kind, sid,
            )
        if (
            spec.blocks_publish_field
            and bool(data.get(spec.blocks_publish_field))
        ):
            any_blocked = True

    if not any_loaded:
        if last_error is not None:
            return PackLoadResult(
                spec=spec, status=PackStatus.ERROR,
                data=None, markdown_path=md_path,
                file_path=primary_file_path,
                error_message=last_error,
            )
        return PackLoadResult(
            spec=spec, status=PackStatus.MISSING,
            data=None, markdown_path=md_path, file_path=None,
        )

    status = PackStatus.BLOCKED if any_blocked else PackStatus.OK
    return PackLoadResult(
        spec=spec, status=status,
        data=primary_data, markdown_path=md_path,
        file_path=primary_file_path,
    )


def load_pack_markdown(path: Path) -> str:
    """Read a Markdown file as text. Returns empty string when the
    file does not exist (defensive)."""

    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


# ---------- helpers ----------


def _entity_file_path(
    root: Path | str, client_slug: str, kind: str, singleton_id: str,
) -> Path:
    """Mirror the JsonFileMemory layout to expose the file path
    even when the pack is MISSING (useful in the UI breadcrumb)."""
    return (
        Path(root) / client_slug / kind / f"{singleton_id}.json"
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
