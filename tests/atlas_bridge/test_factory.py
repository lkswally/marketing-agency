"""Tests for the MKT-8A ATLAS handoff factory — pipeline integration."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.main import main
from core.atlas_bridge import (
    ATLAS_HANDOFF_BRIEF_KIND,
    SINGLETON_ID,
    AtlasHandoffFactory,
    AtlasHandoffKind,
    build_and_persist_atlas_handoff,
)
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _prime(tmp_path: Path) -> str:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    return json.loads(stdout)["client_slug"]


def test_factory_raises_without_strategy_report(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError, match="no CampaignStrategyReport"):
        AtlasHandoffFactory(mem).build(
            client_slug="acme", kind=AtlasHandoffKind.LANDING,
        )


def test_factory_builds_landing_brief(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    handoff = AtlasHandoffFactory(mem).build(
        client_slug=slug, kind=AtlasHandoffKind.LANDING,
    )
    assert handoff.kind is AtlasHandoffKind.LANDING
    assert handoff.landing_brief is not None
    assert handoff.branding_brief is None
    assert handoff.page_design_brief is None
    lb = handoff.landing_brief
    assert lb.sections
    assert lb.primary_cta_label
    # Cross-refs populated from the pipeline.
    assert handoff.strategy_report_id
    assert handoff.creative_pack_id
    assert handoff.visual_pack_id


def test_factory_builds_branding_brief(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    handoff = AtlasHandoffFactory(mem).build(
        client_slug=slug, kind=AtlasHandoffKind.BRANDING,
    )
    assert handoff.kind is AtlasHandoffKind.BRANDING
    assert handoff.branding_brief is not None
    assert handoff.landing_brief is None


def test_factory_builds_page_design_brief(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    handoff = AtlasHandoffFactory(mem).build(
        client_slug=slug, kind=AtlasHandoffKind.PAGE_DESIGN,
        page_name="services",
    )
    assert handoff.kind is AtlasHandoffKind.PAGE_DESIGN
    assert handoff.page_design_brief is not None
    assert handoff.page_design_brief.page_name == "services"


def test_factory_persists_and_audits(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    handoff = build_and_persist_atlas_handoff(
        mem, client_slug=slug, kind=AtlasHandoffKind.LANDING,
    )
    raw = mem.get(slug, ATLAS_HANDOFF_BRIEF_KIND, SINGLETON_ID)
    assert raw["handoff_id"] == handoff.handoff_id
    events = list(mem.read_audit_events(slug))
    assert any(
        "atlas_handoff_brief" in e.payload
        and e.payload["atlas_handoff_brief"]["action"] == "built"
        for e in events
    )


def test_factory_blocks_publish_reflects_upstream(tmp_path: Path) -> None:
    """If approval blocks publish, the handoff carries
    blocks_publish=True so ATLAS can refuse to ship."""
    slug = _prime(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    # MKT-11E: the latest approval, resolved dynamically.
    from core.approval import APPROVAL_PACK_KIND, get_latest_for_client
    pack = get_latest_for_client(mem, slug)
    assert pack is not None
    raw = pack.model_dump(mode="json")
    raw["blocks_publish"] = True
    mem.put(slug, APPROVAL_PACK_KIND, pack.pack_id, raw)
    handoff = AtlasHandoffFactory(mem).build(
        client_slug=slug, kind=AtlasHandoffKind.LANDING,
    )
    assert handoff.blocks_publish is True


def test_factory_does_not_mutate_upstream_packs(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    from core.strategy import REPORT_KIND
    from core.strategy import SINGLETON_ID as STRATEGY_SINGLETON
    before = mem.get(slug, REPORT_KIND, STRATEGY_SINGLETON)
    AtlasHandoffFactory(mem).build(
        client_slug=slug, kind=AtlasHandoffKind.LANDING,
    )
    after = mem.get(slug, REPORT_KIND, STRATEGY_SINGLETON)
    assert before == after


# ---------- safety pins ----------


def test_no_http_lib_in_atlas_bridge_module() -> None:
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "atlas_bridge"
    )
    forbidden = (
        "import requests", "from requests",
        "import httpx", "from httpx",
        "import urllib.request", "from urllib.request",
        "import aiohttp", "from aiohttp",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_atlas_reach_in_anywhere() -> None:
    """Pin: the bridge module must not reference ATLAS core or any
    ATLAS-specific HTTP endpoint."""
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "atlas_bridge"
    )
    forbidden = (
        "atlas_core", "atlas-core", "ATLAS_API_URL",
        "atlas.dispatcher", "from atlas",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_credential_read_in_source() -> None:
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "atlas_bridge"
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in ("os.environ", "os.getenv"):
            assert needle not in text, f"{py.name} contains {needle!r}"
