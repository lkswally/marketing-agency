"""MKT-9B regression tests for ATLAS brief per-kind persistence.

After Alpha Pilot 1 we discovered that running
``mkt atlas-brief --kind landing`` then ``--kind branding`` then
``--kind page_design`` left only the page_design pack persisted
because all three wrote to ``atlas_handoff_brief/current.json``.
The factory now persists per-kind ALSO (in addition to the
legacy ``current`` slot so existing readers keep working).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

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


def test_landing_branding_page_design_all_persist_after_three_runs(
    tmp_path: Path,
) -> None:
    slug = _prime(tmp_path)
    for kind in ("landing", "branding", "page_design"):
        argv = [
            "atlas-brief",
            "--client", slug,
            "--kind", kind,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
        code, _ = _run(argv)
        assert code == 0

    base = tmp_path / "mem" / slug / "atlas_handoff_brief"
    for kind in ("landing", "branding", "page_design"):
        target = base / f"{kind}.json"
        assert target.exists(), f"missing per-kind file: {target}"
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["kind"] == kind, (
            f"file {target} should hold the {kind!r} brief but holds "
            f"{payload['kind']!r}"
        )

    # ``current.json`` still exists (mirrors the last write — page_design).
    current = base / "current.json"
    assert current.exists()
    current_payload = json.loads(current.read_text(encoding="utf-8"))
    assert current_payload["kind"] == "page_design"


def test_per_kind_payloads_are_independent(tmp_path: Path) -> None:
    """Each per-kind slot keeps its own handoff_id — running landing
    twice does NOT change the branding payload."""
    slug = _prime(tmp_path)
    for kind in ("branding", "landing"):
        _run([
            "atlas-brief",
            "--client", slug,
            "--kind", kind,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ])
    base = tmp_path / "mem" / slug / "atlas_handoff_brief"
    branding_first = json.loads(
        (base / "branding.json").read_text(encoding="utf-8")
    )["handoff_id"]
    # Run landing again — branding must stay untouched.
    _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "landing",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    branding_after = json.loads(
        (base / "branding.json").read_text(encoding="utf-8")
    )["handoff_id"]
    assert branding_first == branding_after


def test_portal_loader_finds_atlas_briefs_via_extra_singleton_ids(
    tmp_path: Path,
) -> None:
    """Pin: the portal loader walks ``extra_singleton_ids`` and
    reports OK when at least one per-kind brief is present."""
    from portal.pack_loader import PackStatus, load_pack
    from portal.pack_registry import PORTAL_PACK_REGISTRY

    slug = _prime(tmp_path)
    _run([
        "atlas-brief",
        "--client", slug,
        "--kind", "landing",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out" / slug),
    ])
    atlas_spec = next(
        s for s in PORTAL_PACK_REGISTRY if s.kind == "atlas_handoff_brief"
    )
    result = load_pack(
        root=tmp_path / "mem",
        outputs_dir=tmp_path / "out" / slug,
        client_slug=slug,
        spec=atlas_spec,
    )
    assert result.status is PackStatus.OK
    assert result.data is not None
