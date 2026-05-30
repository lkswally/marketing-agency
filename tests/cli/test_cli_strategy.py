"""CLI tests for `mkt run-strategy`."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def test_run_strategy_succeeds(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["status"] == "succeeded"
    assert payload["client_slug"] == "demo-saas"
    assert payload["report_id"]
    assert payload["envelope_count"] == 11

    # Side effects
    assert (tmp_path / "mem" / "demo-saas").exists()
    md = tmp_path / "out" / "campaign-strategy.md"
    assert md.exists()
    text_md = md.read_text(encoding="utf-8")
    assert "Campaign Strategy Report" in text_md


def test_run_strategy_missing_brief_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-strategy",
            "--brief", str(tmp_path / "nope.json"),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "not found" in text


def test_run_strategy_invalid_brief_fails(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "wrong"}', encoding="utf-8")
    code, text = _run(
        [
            "run-strategy",
            "--brief", str(bad),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    # Pipeline will fail validation during load → returns exception.
    # The CLI catches StrategyPipelineError but not ValidationError, so
    # we expect this to propagate as code 1 or raise. Either way,
    # success would mean we accepted a bad brief — which we must not.
    assert code != 0


def test_run_strategy_writes_to_per_client_outputs(tmp_path: Path) -> None:
    _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    md = tmp_path / "out" / "campaign-strategy.md"
    assert md.exists()
