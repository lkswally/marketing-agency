"""CLI tests for ``mkt atlas-handoff`` (MKT-8A)."""

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


def _prime(tmp_path: Path) -> str:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    return json.loads(stdout)["client_slug"]


def test_atlas_handoff_landing_happy_path(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, stdout = _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "landing",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["kind"] == "landing"
    assert payload["contract_version"] == "atlas-handoff-brief.v1"
    md_path = Path(payload["markdown_path"])
    assert md_path.exists() and md_path.name == "atlas-landing-brief.md"
    md = md_path.read_text(encoding="utf-8")
    assert "ATLAS Handoff" in md
    assert "Landing brief" in md


def test_atlas_handoff_branding_happy_path(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, stdout = _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "branding",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["kind"] == "branding"
    md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Branding brief" in md


def test_atlas_handoff_page_design_happy_path(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, stdout = _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "page_design",
        "--page-name", "pricing",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["kind"] == "page_design"
    md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "pricing" in md


def test_atlas_handoff_exit_2_without_strategy(tmp_path: Path) -> None:
    code, stdout = _run([
        "atlas-brief",
        "--client", "acme",
        "--kind", "landing",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "no CampaignStrategyReport" in stdout


def test_atlas_handoff_rejects_unsupported_kind(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([
            "atlas-brief",
            "--client", "acme",
            "--kind", "robotic_arm",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_atlas_handoff_writes_audit(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, _ = _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "landing",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0
    audit_root = tmp_path / "mem" / slug / "audit"
    content = "\n".join(
        f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl")
    )
    assert "atlas_handoff_brief" in content
    assert "built" in content


def test_atlas_handoff_persists(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, stdout = _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "branding",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    assert code == 0
    payload = json.loads(stdout)
    persisted = (
        tmp_path / "mem" / slug / "atlas_handoff_brief" / "current.json"
    )
    assert persisted.exists()
    raw = json.loads(persisted.read_text(encoding="utf-8"))
    assert raw["handoff_id"] == payload["handoff_id"]
