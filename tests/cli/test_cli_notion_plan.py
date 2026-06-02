"""CLI tests for `mkt notion-plan`."""

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


def _prime_pipeline(tmp_path: Path) -> str:
    """Run the full pipeline + build-tasks so the notion-plan CLI has
    something to consume."""
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0, text
    slug = json.loads(text)["client_slug"]
    code, _ = _run(
        [
            "build-tasks",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    assert code == 0
    return slug


def test_notion_plan_succeeds_from_full_pipeline(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    code, text = _run(
        [
            "notion-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == slug
    assert payload["contract_version"] == "notion-sync-plan.v1"
    assert payload["stats"]["total_tasks"] > 0
    assert payload["rule_set_id"] == "notion-sync-plan-default.v1"


def test_notion_plan_writes_two_files(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    out_dir = tmp_path / "out" / slug
    _, text = _run(
        [
            "notion-plan",
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
    assert "DRY RUN" in md_text
    assert "No Notion API was called" in md_text


def test_notion_plan_missing_task_pack_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "notion-plan",
            "--client", "nonexistent",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no CampaignExecutionTaskPack" in text


def test_notion_plan_records_audit_event(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _run(
        [
            "notion-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    from core.contracts import verify_chain
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events(slug)
    actions = [
        e.payload.get("notion_sync_plan", {}).get("action")
        for e in events
        if "notion_sync_plan" in e.payload
    ]
    assert "planned" in actions
    assert verify_chain(events) == []


def test_notion_plan_persists_to_memory(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _, text = _run(
        [
            "notion-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    payload = json.loads(text)
    from core.memory import JsonFileMemory
    from core.notion_sync import NOTION_SYNC_PLAN_KIND, SINGLETON_ID

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists(slug, NOTION_SYNC_PLAN_KIND, SINGLETON_ID)
    raw = mem.get(slug, NOTION_SYNC_PLAN_KIND, SINGLETON_ID)
    assert raw["plan_id"] == payload["plan_id"]
