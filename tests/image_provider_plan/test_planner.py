"""Tests for the MKT-7B provider planner — integration via pipeline."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.main import main
from core.approval import APPROVAL_PACK_KIND
from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
from core.image_jobs import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    ImageJobFactory,
)
from core.image_jobs import (
    SINGLETON_ID as JOB_PACK_SINGLETON,
)
from core.image_provider_plan import (
    IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND,
    SINGLETON_ID,
    ImageProviderPlanner,
    ProviderDryRunStatus,
    build_and_persist_provider_plan,
)
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _prime_pipeline_and_image_jobs(tmp_path: Path) -> str:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    slug = json.loads(stdout)["client_slug"]
    # Build the MKT-7A job pack so the MKT-7B planner has data.
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    mem.put(slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON,
            pack.model_dump(mode="json"))
    return slug


# ---------- raises ----------


def test_planner_raises_without_job_pack(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError, match="no ImageGenerationJobPack"):
        ImageProviderPlanner(mem).plan("acme")


# ---------- happy path ----------


def test_planner_produces_recommendation_per_job(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageProviderPlanner(mem).plan(slug)
    assert pack.client_slug == slug
    assert pack.stats.total_jobs > 0
    # One recommendation + one receipt per job.
    assert len(pack.recommendations) == pack.stats.total_jobs
    assert len(pack.dry_run_receipts) == pack.stats.total_jobs
    # Every recommended provider is one of the supported set.
    valid_providers = {
        "openai_images", "replicate", "stability_ai",
        "midjourney", "canva", "figma", "manual",
    }
    for r in pack.recommendations:
        assert r.recommended_provider in valid_providers
        assert r.fallback_provider == "manual"


def test_planner_evaluations_include_all_providers(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageProviderPlanner(mem).plan(slug)
    eval_names = {e.provider for e in pack.evaluations}
    assert eval_names == {
        "openai_images", "replicate", "stability_ai",
        "midjourney", "canva", "figma", "manual",
    }


def test_planner_evaluations_carry_credentials_names(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageProviderPlanner(mem).plan(slug)
    openai = next(e for e in pack.evaluations if e.provider == "openai_images")
    assert "OPENAI_API_KEY" in openai.credentials_required


def test_planner_dry_run_status_is_only_dry_run_or_skipped(tmp_path: Path) -> None:
    """Pin: v1 of the contract never emits a real-call status."""
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageProviderPlanner(mem).plan(slug)
    valid = {
        ProviderDryRunStatus.DRY_RUN,
        ProviderDryRunStatus.SKIPPED_BLOCKED,
        ProviderDryRunStatus.SKIPPED_MANUAL,
    }
    for r in pack.dry_run_receipts:
        assert r.status in valid


def test_planner_skipped_when_job_blocked_by_approval(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    # Flip approval to blocks_publish=True and rebuild the job pack.
    mem = JsonFileMemory(tmp_path / "mem")
    raw = mem.get(slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON)
    raw["blocks_publish"] = True
    mem.put(slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON, raw)
    new_job_pack = ImageJobFactory(mem).build(slug)
    mem.put(slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON,
            new_job_pack.model_dump(mode="json"))

    plan = ImageProviderPlanner(mem).plan(slug)
    assert plan.blocks_publish is True
    assert plan.stats.skipped_blocked == plan.stats.total_jobs
    for r in plan.dry_run_receipts:
        assert r.status is ProviderDryRunStatus.SKIPPED_BLOCKED
        assert r.reason


def test_planner_persists_and_audits(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = build_and_persist_provider_plan(mem, client_slug=slug)
    raw = mem.get(slug, IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND, SINGLETON_ID)
    assert raw["pack_id"] == pack.pack_id
    events = list(mem.read_audit_events(slug))
    assert any(
        "image_provider_recommendation_pack" in e.payload
        and e.payload["image_provider_recommendation_pack"]["action"] == "planned"
        for e in events
    )


def test_planner_is_deterministic(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    a = ImageProviderPlanner(mem).plan(slug)
    b = ImageProviderPlanner(mem).plan(slug)
    a_seq = [(r.job_id, r.recommended_provider, r.recommended_score)
             for r in a.recommendations]
    b_seq = [(r.job_id, r.recommended_provider, r.recommended_score)
             for r in b.recommendations]
    assert a_seq == b_seq


def test_planner_cost_estimate_is_non_negative(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageProviderPlanner(mem).plan(slug)
    assert pack.stats.total_estimated_cost_usd >= 0
    for r in pack.recommendations:
        assert r.estimated_cost_usd >= 0


def test_planner_records_override_count(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageProviderPlanner(mem).plan(slug)
    # ``overrode_job_suggestion`` is the count of jobs where the
    # planner picked a different provider than the MKT-7A hint.
    # It must equal the number of mismatches in the recommendation
    # list.
    expected = sum(
        1 for r in pack.recommendations
        if r.recommended_provider != r.job_provider_suggestion
    )
    assert pack.stats.overrode_job_suggestion == expected


def test_planner_does_not_mutate_job_pack(tmp_path: Path) -> None:
    slug = _prime_pipeline_and_image_jobs(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    before = mem.get(slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON)
    ImageProviderPlanner(mem).plan(slug)
    after = mem.get(slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON)
    assert before == after


# ---------- safety pins ----------


def test_no_provider_sdk_imported_anywhere() -> None:
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "image_provider_plan"
    )
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


def test_no_http_lib_in_provider_plan_module() -> None:
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "image_provider_plan"
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


def test_no_credential_read_in_source() -> None:
    """Pin: the planner must not read env vars. It documents which
    env vars a future integration would need, but never reads them."""
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "image_provider_plan"
    )
    forbidden = (
        "os.environ", "os.getenv",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"
