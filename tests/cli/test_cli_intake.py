"""CLI tests for `mkt intake`."""

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


def test_intake_demo_succeeds(tmp_path: Path) -> None:
    code, text = _run(
        [
            "intake",
            "--file", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == "acme-bootstrapped"
    assert payload["is_valid"] is True
    assert payload["can_normalize"] is True
    assert payload["missing_critical"] == 0

    # Disk side effects
    intake_path = Path(payload["intake_path"])
    summary_path = Path(payload["summary_path"])
    brief_path = Path(payload["brief_path"])
    assert intake_path.exists()
    assert summary_path.exists()
    assert brief_path.exists()

    # Memory persistence
    assert (tmp_path / "mem" / "acme-bootstrapped" / "client_intake" / "current.json").exists()
    assert (tmp_path / "mem" / "acme-bootstrapped" / "intake_validation" / "current.json").exists()


def test_intake_missing_file_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "intake",
            "--file", str(tmp_path / "nope.json"),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "not found" in text


def test_intake_invalid_json_fails(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code, text = _run(
        [
            "intake",
            "--file", str(bad),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "invalid intake" in text


def test_intake_strict_blocks_on_critical(tmp_path: Path) -> None:
    # Intake missing product_or_service + commercial_objective + audience.
    minimal = tmp_path / "minimal.json"
    minimal.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )
    code, text = _run(
        [
            "intake",
            "--file", str(minimal),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--strict",
        ]
    )
    assert code == 4
    assert "critical issues present" in text


def test_intake_without_strict_succeeds_even_with_critical(tmp_path: Path) -> None:
    """Without ``--strict`` the command exits 0 even when critical issues exist;
    just no brief.json is written."""
    minimal = tmp_path / "minimal.json"
    minimal.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )
    code, text = _run(
        [
            "intake",
            "--file", str(minimal),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["is_valid"] is False
    assert payload["brief_path"] is None
    # Summary still written so the reviewer can fix.
    assert Path(payload["summary_path"]).exists()


def test_intake_brief_is_run_strategy_compatible(tmp_path: Path) -> None:
    """End-to-end: intake produces a brief.json that `run-strategy` accepts."""
    code, _ = _run(
        [
            "intake",
            "--file", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    brief_path = tmp_path / "out" / "acme-bootstrapped" / "brief.json"
    assert brief_path.exists()

    # Now run-strategy on the produced brief.
    code, text = _run(
        [
            "run-strategy",
            "--brief", str(brief_path),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out2"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["status"] == "succeeded"
    assert payload["client_slug"] == "acme-bootstrapped"


def test_audit_trail_records_intake_action(tmp_path: Path) -> None:
    _run(
        [
            "intake",
            "--file", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    from core.contracts import verify_chain
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme-bootstrapped")
    actions = [
        e.payload.get("intake", {}).get("action")
        for e in events
        if "intake" in e.payload
    ]
    assert "created" in actions
    assert verify_chain(events) == []
