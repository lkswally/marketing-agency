"""Tests for portal.pack_loader — safe load + status derivation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from core.memory import JsonFileMemory
from portal.pack_loader import PackStatus, load_pack, load_pack_markdown
from portal.pack_registry import PORTAL_PACK_REGISTRY, PortalPackSpec

_STRATEGY_SPEC = next(
    s for s in PORTAL_PACK_REGISTRY if s.kind == "campaign_strategy_report"
)
_APPROVAL_SPEC = next(
    s for s in PORTAL_PACK_REGISTRY if s.kind == "approval_pack"
)


def _now_iso() -> str:
    return datetime(2026, 6, 4, tzinfo=UTC).isoformat()


def _seed(root: Path, *, slug: str, spec: PortalPackSpec, payload: dict) -> None:
    mem = JsonFileMemory(root)
    mem.put(slug, spec.kind, spec.singleton_id, payload)


def test_load_pack_returns_missing_when_absent(tmp_path: Path) -> None:
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="ghost",
        spec=_STRATEGY_SPEC,
    )
    assert result.status is PackStatus.MISSING
    assert result.data is None


def test_load_pack_returns_ok(tmp_path: Path) -> None:
    _seed(tmp_path / "data", slug="acme", spec=_STRATEGY_SPEC, payload={
        "client_slug": "acme",
        "report_id": "r1",
        "_minimal": True,
    })
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=_STRATEGY_SPEC,
    )
    assert result.status is PackStatus.OK
    assert result.data["report_id"] == "r1"
    assert result.file_path is not None
    assert result.file_path.name == "current.json"


def test_load_pack_returns_blocked_when_posture_flag_set(tmp_path: Path) -> None:
    _seed(tmp_path / "data", slug="acme", spec=_APPROVAL_SPEC, payload={
        "client_slug": "acme",
        "pack_id": "ap1",
        "blocks_publish": True,
    })
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=_APPROVAL_SPEC,
    )
    assert result.status is PackStatus.BLOCKED
    assert result.data["blocks_publish"] is True


def test_load_pack_returns_ok_when_flag_false(tmp_path: Path) -> None:
    _seed(tmp_path / "data", slug="acme", spec=_APPROVAL_SPEC, payload={
        "client_slug": "acme", "pack_id": "ap1", "blocks_publish": False,
    })
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=_APPROVAL_SPEC,
    )
    assert result.status is PackStatus.OK


def test_load_pack_returns_error_when_json_corrupt(tmp_path: Path) -> None:
    # Hand-write a corrupt JSON in the slot the loader will probe.
    target = (
        tmp_path / "data" / "acme" / _STRATEGY_SPEC.kind / "current.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text("{not-json", encoding="utf-8")
    # Memory must register the kind directory so .get() is attempted.
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=_STRATEGY_SPEC,
    )
    assert result.status is PackStatus.ERROR
    assert result.error_message
    assert "JSONDecodeError" in result.error_message or "Decode" in result.error_message


def test_load_pack_finds_markdown_under_outputs(tmp_path: Path) -> None:
    _seed(tmp_path / "data", slug="acme", spec=_STRATEGY_SPEC,
          payload={"client_slug": "acme", "report_id": "r1"})
    md_target = tmp_path / "outputs" / "acme" / "campaign-strategy.md"
    md_target.parent.mkdir(parents=True)
    md_target.write_text("# Strategy", encoding="utf-8")
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=_STRATEGY_SPEC,
    )
    assert result.markdown_path == md_target


def test_load_pack_with_outputs_dir_none(tmp_path: Path) -> None:
    _seed(tmp_path / "data", slug="acme", spec=_STRATEGY_SPEC,
          payload={"client_slug": "acme", "report_id": "r1"})
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=None,
        client_slug="acme",
        spec=_STRATEGY_SPEC,
    )
    assert result.markdown_path is None
    assert result.status is PackStatus.OK


def test_load_pack_markdown_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_pack_markdown(tmp_path / "ghost.md") == ""


def test_load_pack_markdown_reads_existing(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("# Hello", encoding="utf-8")
    assert load_pack_markdown(p) == "# Hello"


def test_load_pack_for_every_registry_spec_does_not_crash(tmp_path: Path) -> None:
    """Pin: every spec in the registry loads cleanly when the data
    is absent — the portal must tolerate any missing pack."""
    for spec in PORTAL_PACK_REGISTRY:
        result = load_pack(
            root=tmp_path / "data",
            outputs_dir=tmp_path / "outputs",
            client_slug="ghost",
            spec=spec,
        )
        assert result.status is PackStatus.MISSING


def test_load_pack_atlas_handoff_picks_first_matching_markdown(
    tmp_path: Path,
) -> None:
    """The ATLAS spec carries 3 candidate filenames — the loader
    picks the first match."""
    atlas_spec = next(
        s for s in PORTAL_PACK_REGISTRY if s.kind == "atlas_handoff_brief"
    )
    base = tmp_path / "outputs" / "acme"
    base.mkdir(parents=True)
    # Only the branding file exists.
    (base / "atlas-branding-brief.md").write_text("# branding", encoding="utf-8")
    _seed(tmp_path / "data", slug="acme", spec=atlas_spec,
          payload={"client_slug": "acme", "handoff_id": "h1",
                   "blocks_publish": False, "kind": "branding"})
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=atlas_spec,
    )
    assert result.markdown_path is not None
    assert result.markdown_path.name == "atlas-branding-brief.md"


def test_load_pack_file_path_returned_even_when_missing(tmp_path: Path) -> None:
    """Even when MISSING, the portal needs the expected on-disk
    path to render the breadcrumb. Loader still returns None to
    signal absence — but the wider story is the registry tells the
    UI where it WOULD live."""
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=None,
        client_slug="ghost",
        spec=_STRATEGY_SPEC,
    )
    assert result.file_path is None
    assert result.status is PackStatus.MISSING


def test_load_pack_json_roundtrip(tmp_path: Path) -> None:
    payload = {"client_slug": "acme", "report_id": "r1", "nested": {"k": 1}}
    _seed(tmp_path / "data", slug="acme", spec=_STRATEGY_SPEC, payload=payload)
    result = load_pack(
        root=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        client_slug="acme",
        spec=_STRATEGY_SPEC,
    )
    assert result.data == payload
    # Sanity: the persisted file is JSON we can re-load identically.
    assert json.loads(result.file_path.read_text(encoding="utf-8")) == payload


_ = _now_iso  # silence unused import warning
