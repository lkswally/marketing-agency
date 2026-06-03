"""CLI tests for `mkt import-metrics` and `mkt analyze-metrics`."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


# ---------- import-metrics ----------

def test_import_ga4_csv_succeeds(tmp_path: Path) -> None:
    code, text = _run(
        [
            "import-metrics",
            "--client", "acme",
            "--file", str(FIXTURES / "ga4_demo.csv"),
            "--source", "ga4",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["source"] == "ga4"
    assert payload["rows_imported"] > 0


def test_import_missing_file_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "import-metrics",
            "--client", "acme",
            "--file", str(tmp_path / "nope.csv"),
            "--source", "ga4",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "file not found" in text


def test_import_invalid_extension_returns_exit_2(tmp_path: Path) -> None:
    bad = tmp_path / "data.txt"
    bad.write_text("x", encoding="utf-8")
    code, text = _run(
        [
            "import-metrics",
            "--client", "acme",
            "--file", str(bad),
            "--source", "ga4",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "unsupported" in text


def test_import_writes_md_and_json(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    _, text = _run(
        [
            "import-metrics",
            "--client", "acme",
            "--file", str(FIXTURES / "ga4_demo.csv"),
            "--source", "ga4",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(out_dir),
        ]
    )
    payload = json.loads(text)
    md = Path(payload["markdown_path"])
    js = Path(payload["json_path"])
    assert md.exists()
    assert js.exists()


# ---------- analyze-metrics ----------

def _import_all(tmp_path: Path, client: str = "acme") -> None:
    for fixture, source in [
        ("ga4_demo.csv", "ga4"),
        ("sc_demo.csv", "search_console"),
        ("social_demo.csv", "social"),
        ("email_demo.csv", "email"),
    ]:
        code, _ = _run(
            [
                "import-metrics",
                "--client", client,
                "--file", str(FIXTURES / fixture),
                "--source", source,
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )
        assert code == 0


def test_analyze_after_imports_succeeds(tmp_path: Path) -> None:
    _import_all(tmp_path)
    code, text = _run(
        [
            "analyze-metrics",
            "--client", "acme",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["best_channel"]
    assert payload["recommendations"] > 0


def test_analyze_without_snapshot_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "analyze-metrics",
            "--client", "ghost",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "MetricsSnapshot" in text


def test_analyze_writes_md_and_json(tmp_path: Path) -> None:
    _import_all(tmp_path)
    out_dir = tmp_path / "out"
    _, text = _run(
        [
            "analyze-metrics",
            "--client", "acme",
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
    assert "Mejor canal" in md_text


def test_analyze_records_audit_event(tmp_path: Path) -> None:
    _import_all(tmp_path)
    _run(
        [
            "analyze-metrics",
            "--client", "acme",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    from core.contracts import verify_chain
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme")
    actions = [
        e.payload.get("analytics_analysis", {}).get("action")
        for e in events
        if "analytics_analysis" in e.payload
    ]
    assert "analyzed" in actions
    assert verify_chain(events) == []
