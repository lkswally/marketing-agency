"""CLI tests for ``mkt image-provider-plan`` (MKT-7B)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.main import main
from core.image_jobs import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    ImageJobFactory,
)
from core.image_jobs import (
    SINGLETON_ID as JOB_PACK_SINGLETON,
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
    slug = json.loads(stdout)["client_slug"]
    mem = JsonFileMemory(tmp_path / "mem")
    pack = ImageJobFactory(mem).build(slug)
    mem.put(slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON,
            pack.model_dump(mode="json"))
    return slug


def test_image_provider_plan_happy_path(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, stdout = _run([
        "image-provider-plan",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["client_slug"] == slug
    assert payload["contract_version"] == "image-provider-recommendation-pack.v1"
    assert payload["stats"]["total_jobs"] > 0
    assert payload["stats"]["total_estimated_cost_usd"] >= 0
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["json_path"]).exists()
    md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Image Provider Plan" in md
    assert "Pure analysis" in md


def test_image_provider_plan_exit_2_without_job_pack(tmp_path: Path) -> None:
    code, stdout = _run([
        "image-provider-plan",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "no ImageGenerationJobPack" in stdout


def test_image_provider_plan_missing_client(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([
            "image-provider-plan",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_image_provider_plan_writes_audit(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, _ = _run([
        "image-provider-plan",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0
    audit_root = tmp_path / "mem" / slug / "audit"
    content = "\n".join(
        f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl")
    )
    assert "image_provider_recommendation_pack" in content
    assert "planned" in content


def test_image_provider_plan_persists(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, stdout = _run([
        "image-provider-plan",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0
    payload = json.loads(stdout)
    persisted = (
        tmp_path / "mem" / slug / "image_provider_recommendation_pack"
        / "current.json"
    )
    assert persisted.exists()
    raw = json.loads(persisted.read_text(encoding="utf-8"))
    assert raw["pack_id"] == payload["pack_id"]
