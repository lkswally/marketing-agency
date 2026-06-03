"""CLI tests for `mkt n8n-plan`."""

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
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    return json.loads(text)["client_slug"]


def test_n8n_plan_succeeds(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, text = _run(
        [
            "n8n-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == slug
    assert payload["contract_version"] == "n8n-execution-payload.v1"
    assert payload["stats"]["total_actions"] > 0


def test_writes_md_and_json_files(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    out_dir = tmp_path / "out" / slug
    _, text = _run(
        [
            "n8n-plan",
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
    assert "No HTTP call was made" in md_text


def test_missing_run_summary_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "n8n-plan",
            "--client", "ghost-client",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no CampaignRunSummary" in text


def test_persists_to_memory_and_audit(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    _, text = _run(
        [
            "n8n-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    payload = json.loads(text)
    from core.memory import JsonFileMemory
    from core.n8n_sync import N8N_EXECUTION_PAYLOAD_KIND, SINGLETON_ID

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists(slug, N8N_EXECUTION_PAYLOAD_KIND, SINGLETON_ID)
    raw = mem.get(slug, N8N_EXECUTION_PAYLOAD_KIND, SINGLETON_ID)
    assert raw["payload_id"] == payload["payload_id"]
    events = mem.read_audit_events(slug)
    actions = [
        e.payload.get("n8n_execution_payload", {}).get("action")
        for e in events
        if "n8n_execution_payload" in e.payload
    ]
    assert "planned" in actions
