"""Tests for the ImageJobFactory — integration via the full pipeline."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.main import main
from core.approval import APPROVAL_PACK_KIND
from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
from core.creative.models import CreativeAssetState
from core.image_jobs import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    SINGLETON_ID,
    ImageJobFactory,
    ImageJobState,
    ImageProviderSuggestion,
    build_and_persist_image_jobs,
)
from core.memory import JsonFileMemory
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import (
    VISUAL_PACK_KIND,
    VisualDirectionPack,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _prime_pipeline(tmp_path: Path) -> str:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    return json.loads(stdout)["client_slug"]


# ---------- raises ----------


def test_factory_raises_without_visual_pack(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError, match="no VisualDirectionPack"):
        ImageJobFactory(mem).build("acme")


# ---------- happy path ----------


def test_factory_builds_jobs_from_pipeline(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    assert pack.client_slug == slug
    assert pack.visual_pack_id
    # The demo pipeline produces multiple piece visual directions
    # with multiple prompt variants each.
    assert pack.stats.total_jobs > 0
    assert pack.stats.directions_consumed > 0
    # No job is GENERATED (factory pin).
    for j in pack.jobs:
        assert j.state is not ImageJobState.GENERATED


def test_factory_never_emits_generated(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    by_state = pack.stats.by_state
    assert by_state.get("generated", 0) == 0


def test_factory_persists_and_audits(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = build_and_persist_image_jobs(mem, client_slug=slug)

    raw = mem.get(slug, IMAGE_GENERATION_JOB_PACK_KIND, SINGLETON_ID)
    assert raw["pack_id"] == pack.pack_id

    events = list(mem.read_audit_events(slug))
    assert any(
        "image_generation_job_pack" in e.payload
        and e.payload["image_generation_job_pack"]["action"] == "built"
        for e in events
    )


def test_factory_provider_suggestion_is_deterministic(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    mem_a = JsonFileMemory(tmp_path / "mem")
    pack_a = ImageJobFactory(mem_a).build(slug)
    # Run a second time on the same memory; provider suggestions
    # should be identical per (piece_type, variant_id).
    pack_b = ImageJobFactory(mem_a).build(slug)
    by_a = sorted(
        (j.piece_type, j.variant_id, j.provider_suggestion.value)
        for j in pack_a.jobs
    )
    by_b = sorted(
        (j.piece_type, j.variant_id, j.provider_suggestion.value)
        for j in pack_b.jobs
    )
    assert by_a == by_b


def test_filename_suggestion_uses_client_slug(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    for j in pack.jobs:
        assert j.output_filename_suggestion.startswith(slug + "--")
        assert j.output_filename_suggestion.endswith(".png")


def test_provider_suggestion_matches_piece_type_heuristic(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    expected = {
        "instagram_post": ImageProviderSuggestion.REPLICATE,
        "instagram_story": ImageProviderSuggestion.REPLICATE,
        "instagram_carousel": ImageProviderSuggestion.REPLICATE,
        "linkedin_post_graphic": ImageProviderSuggestion.CANVA,
        "facebook_post": ImageProviderSuggestion.CANVA,
        "email_header": ImageProviderSuggestion.OPENAI_IMAGES,
        "landing_hero": ImageProviderSuggestion.OPENAI_IMAGES,
        "flyer_square": ImageProviderSuggestion.MIDJOURNEY,
        "flyer_vertical": ImageProviderSuggestion.MIDJOURNEY,
        "ad_creative": ImageProviderSuggestion.MIDJOURNEY,
        "reels_cover": ImageProviderSuggestion.REPLICATE,
    }
    for j in pack.jobs:
        if j.piece_type in expected:
            assert j.provider_suggestion is expected[j.piece_type]


# ---------- approval blocking ----------


def _force_approval_blocks(tmp_path: Path, slug: str) -> None:
    """Mutate the persisted ApprovalPack so blocks_publish=True."""
    mem = JsonFileMemory(tmp_path / "mem")
    raw = mem.get(slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON)
    raw["blocks_publish"] = True
    mem.put(slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON, raw)


def test_factory_marks_all_jobs_blocked_when_approval_blocks(
    tmp_path: Path,
) -> None:
    slug = _prime_pipeline(tmp_path)
    _force_approval_blocks(tmp_path, slug)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    assert pack.blocks_publish is True
    assert pack.stats.total_jobs > 0
    for j in pack.jobs:
        assert j.state is ImageJobState.BLOCKED
        assert "Approval pack" in (j.blocked_reason or "")
    assert pack.stats.blocked_due_to_approval == pack.stats.total_jobs


# ---------- direction blocking ----------


def _force_one_direction_blocked(tmp_path: Path, slug: str) -> str:
    """Set the first PieceVisualDirection.state = BLOCKED. Returns
    the direction_id mutated."""

    mem = JsonFileMemory(tmp_path / "mem")
    raw = mem.get(slug, VISUAL_PACK_KIND, VISUAL_SINGLETON)
    pack = VisualDirectionPack.model_validate(raw)
    blocked_dir_id = pack.directions[0].direction_id
    pack.directions[0] = pack.directions[0].model_copy(
        update={"state": CreativeAssetState.BLOCKED},
    )
    mem.put(slug, VISUAL_PACK_KIND, VISUAL_SINGLETON,
            pack.model_dump(mode="json"))
    return blocked_dir_id


def test_factory_marks_only_affected_jobs_blocked_by_direction(
    tmp_path: Path,
) -> None:
    slug = _prime_pipeline(tmp_path)
    blocked_dir_id = _force_one_direction_blocked(tmp_path, slug)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    affected = [j for j in pack.jobs if j.direction_id == blocked_dir_id]
    others = [j for j in pack.jobs if j.direction_id != blocked_dir_id]
    assert affected
    for j in affected:
        assert j.state is ImageJobState.BLOCKED
        assert "Source visual direction" in (j.blocked_reason or "")
    # Other jobs are not BLOCKED by direction (may still be NEEDS_REVIEW
    # / DRAFT — we just check they're not BLOCKED).
    for j in others:
        assert j.state is not ImageJobState.BLOCKED


# ---------- safety pins ----------


def test_no_provider_sdk_imported_anywhere() -> None:
    """The image_jobs module must not import any image provider SDK."""
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "image_jobs"
    )
    # Forbidden: SDK / library imports + image manipulation calls.
    # The enum values "midjourney" / "canva" / "figma" as STRING
    # LITERALS are legitimate provider hints; we don't ban them.
    forbidden = (
        "import openai",
        "from openai",
        "import replicate",
        "from replicate",
        "stability_sdk",
        "from PIL",
        "import PIL",
        "Image.open",
        "Image.save",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_http_lib_in_image_jobs_module() -> None:
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "image_jobs"
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


def test_factory_source_has_no_generated_emission() -> None:
    """Pin: the factory source must not assign ``ImageJobState.GENERATED``
    anywhere — only deserialisation can produce it."""
    import pathlib

    factory_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "image_jobs" / "factory.py"
    )
    text = factory_path.read_text(encoding="utf-8")
    assert "ImageJobState.GENERATED" not in text
