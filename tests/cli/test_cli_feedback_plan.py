"""CLI tests for `mkt feedback-plan`."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _prime(tmp_path: Path) -> str:
    """Run a campaign + analytics imports + analyze so feedback-plan
    has what it needs."""
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    slug = json.loads(text)["client_slug"]
    for fixture, source in [
        ("ga4_demo.csv", "ga4"),
        ("sc_demo.csv", "search_console"),
        ("social_demo.csv", "social"),
        ("email_demo.csv", "email"),
    ]:
        assert _run(
            [
                "import-metrics",
                "--client", slug,
                "--file", str(FIXTURES / fixture),
                "--source", source,
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )[0] == 0
    assert _run(
        [
            "analyze-metrics",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )[0] == 0
    return slug


def test_feedback_plan_succeeds(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, text = _run(
        [
            "feedback-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == slug
    assert payload["contract_version"] == "campaign-feedback-pack.v1"
    assert payload["stats"]["total_items"] > 0


def test_feedback_plan_writes_md_and_json(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    out_dir = tmp_path / "out"
    _, text = _run(
        [
            "feedback-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(out_dir),
        ]
    )
    payload = json.loads(text)
    md = Path(payload["markdown_path"])
    js = Path(payload["json_path"])
    assert md.exists()
    assert js.exists()
    md_text = md.read_text(encoding="utf-8")
    assert "Campaign Feedback Pack" in md_text


def test_feedback_plan_missing_rec_pack_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "feedback-plan",
            "--client", "ghost",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "OptimizationRecommendationPack" in text


def test_feedback_plan_persists_and_audits(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    _, text = _run(
        [
            "feedback-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    payload = json.loads(text)
    from core.feedback import CAMPAIGN_FEEDBACK_PACK_KIND, SINGLETON_ID
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists(slug, CAMPAIGN_FEEDBACK_PACK_KIND, SINGLETON_ID)
    raw = mem.get(slug, CAMPAIGN_FEEDBACK_PACK_KIND, SINGLETON_ID)
    assert raw["pack_id"] == payload["pack_id"]
    events = mem.read_audit_events(slug)
    actions = [
        e.payload.get("campaign_feedback_pack", {}).get("action")
        for e in events
        if "campaign_feedback_pack" in e.payload
    ]
    assert "planned" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []
