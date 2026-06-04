"""CLI tests for ``mkt image-jobs``."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.main import main

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


def test_image_jobs_happy_path(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    code, stdout = _run([
        "image-jobs",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["client_slug"] == slug
    assert payload["contract_version"] == "image-generation-job-pack.v1"
    assert payload["stats"]["total_jobs"] > 0
    # No "generated" state in by_state map.
    assert payload["stats"]["by_state"].get("generated", 0) == 0
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["json_path"]).exists()
    md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Image Generation Jobs" in md
    assert "No provider was called" in md


def test_image_jobs_exit_2_without_visual_pack(tmp_path: Path) -> None:
    code, stdout = _run([
        "image-jobs",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "no VisualDirectionPack" in stdout


def test_image_jobs_missing_client_arg(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([
            "image-jobs",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_image_jobs_writes_audit(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    code, _ = _run([
        "image-jobs",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0
    audit_root = tmp_path / "mem" / slug / "audit"
    assert audit_root.exists()
    content = "\n".join(
        f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl")
    )
    assert "image_generation_job_pack" in content
    assert "built" in content


def test_image_jobs_persists_pack(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    code, stdout = _run([
        "image-jobs",
        "--client", slug,
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0
    payload = json.loads(stdout)
    pack_dir = tmp_path / "mem" / slug / "image_generation_job_pack"
    assert (pack_dir / "current.json").exists()
    raw = json.loads((pack_dir / "current.json").read_text(encoding="utf-8"))
    assert raw["pack_id"] == payload["pack_id"]
