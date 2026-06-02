"""CLI tests for `mkt build-tasks`."""

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
    """Run the full campaign pipeline so the artifacts the
    build-tasks CLI consumes exist in memory."""
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0, text
    payload = json.loads(text)
    return payload["client_slug"]


def test_build_tasks_succeeds_from_pipeline_output(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    code, text = _run(
        [
            "build-tasks",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == slug
    assert payload["total_tasks"] > 0
    assert payload["rule_set_id"] == "execution-task-default.v1"


def test_build_tasks_writes_three_files(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    out_dir = tmp_path / "out" / slug
    _, text = _run(
        [
            "build-tasks",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(out_dir),
        ]
    )
    payload = json.loads(text)
    md = Path(payload["markdown_path"])
    js = Path(payload["json_path"])
    notion = Path(payload["notion_payload_path"])
    assert md.exists()
    assert js.exists()
    assert notion.exists()
    # Notion payload is valid JSON with the expected top-level keys.
    nd = json.loads(notion.read_text(encoding="utf-8"))
    assert set(nd.keys()) == {"schema_version", "source_pack", "database", "pages"}


def test_build_tasks_missing_strategy_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "build-tasks",
            "--client", "nonexistent-client",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no CampaignStrategyReport" in text


def test_build_tasks_records_audit_event(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _run(
        [
            "build-tasks",
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
        e.payload.get("execution_task_pack", {}).get("action")
        for e in events
        if "execution_task_pack" in e.payload
    ]
    assert "built" in actions
    assert verify_chain(events) == []


def test_build_tasks_persists_pack(tmp_path: Path) -> None:
    slug = _prime_pipeline(tmp_path)
    _, text = _run(
        [
            "build-tasks",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    payload = json.loads(text)
    from core.execution import EXECUTION_TASK_PACK_KIND, SINGLETON_ID
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists(slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
    raw = mem.get(slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
    assert raw["pack_id"] == payload["pack_id"]
