"""CLI tests for `mkt apply-feedback`."""

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
    for cmd in ("analyze-metrics", "feedback-plan"):
        assert _run(
            [
                cmd,
                "--client", slug,
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )[0] == 0
    return slug


def test_apply_feedback_succeeds(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, text = _run(
        [
            "apply-feedback",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == slug
    assert payload["contract_version"] == "next-campaign-iteration-plan.v1"
    assert payload["stats"]["total_items"] > 0


def test_apply_feedback_writes_md_and_json(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    out_dir = tmp_path / "out"
    _, text = _run(
        [
            "apply-feedback",
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
    assert "Next Campaign Iteration Plan" in md_text


def test_apply_feedback_missing_pack_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "apply-feedback",
            "--client", "ghost",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "CampaignFeedbackPack" in text


def test_apply_feedback_persists_and_audits(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    _, text = _run(
        [
            "apply-feedback",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    payload = json.loads(text)
    from core.iteration import NEXT_CAMPAIGN_ITERATION_PLAN_KIND, SINGLETON_ID
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists(slug, NEXT_CAMPAIGN_ITERATION_PLAN_KIND, SINGLETON_ID)
    raw = mem.get(slug, NEXT_CAMPAIGN_ITERATION_PLAN_KIND, SINGLETON_ID)
    assert raw["plan_id"] == payload["plan_id"]
    events = mem.read_audit_events(slug)
    actions = [
        e.payload.get("next_campaign_iteration_plan", {}).get("action")
        for e in events
        if "next_campaign_iteration_plan" in e.payload
    ]
    assert "planned" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []
