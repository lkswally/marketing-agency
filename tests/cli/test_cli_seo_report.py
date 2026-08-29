"""CLI tests for ``mkt seo-report`` (MKT-10C)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.main import main


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _write_evidence(path: Path) -> Path:
    payload = {
        "client_slug": "acme",
        "keyword_research": [
            {"keyword": "crm legal", "search_intent": "transactional", "search_volume": 100}
        ],
        "url_structure": ["/es/blog/a", "/es/blog/b"],
        "technical_notes": ["canonical tags missing on /blog/*"],
    }
    file_path = path / "evidence.json"
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    return file_path


def test_seo_report_happy_path_no_evidence(tmp_path: Path) -> None:
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["client_slug"] == "acme"
    assert payload["missing_evidence_count"] > 0
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["json_path"]).exists()


def test_seo_report_with_input_evidence(tmp_path: Path) -> None:
    evidence_path = _write_evidence(tmp_path)
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--input", str(evidence_path),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "SEO Intelligence Report" in md


def test_seo_report_invalid_input_file_exits_2(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--input", str(bad_path),
    ])
    assert code == 2
    assert "invalid --input" in stdout


def test_seo_report_missing_input_file_exits_2(tmp_path: Path) -> None:
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--input", str(tmp_path / "nope.json"),
    ])
    assert code == 2
    assert "file not found" in stdout


def test_seo_report_dry_run_does_not_persist_or_write(tmp_path: Path) -> None:
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--dry-run",
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["dry_run"] is True
    assert not (tmp_path / "out" / "seo-intelligence-report.md").exists()
    assert not (tmp_path / "mem").exists() or not list((tmp_path / "mem").glob("**/*"))


def test_seo_report_overwrite_protection(tmp_path: Path) -> None:
    code1, _ = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert code1 == 0

    code2, stdout2 = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert code2 == 2
    assert "overwrite" in stdout2

    code3, stdout3 = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--overwrite",
    ])
    assert code3 == 0, stdout3


def test_seo_report_period_flags(tmp_path: Path) -> None:
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--start-date", "2026-01-01",
        "--end-date", "2026-01-31",
        "--period-label", "2026-01",
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["period_start"] == "2026-01-01"
    assert payload["period_end"] == "2026-01-31"
    assert payload["period_label"] == "2026-01"


def test_seo_report_invalid_start_date_exits_2(tmp_path: Path) -> None:
    code, stdout = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
        "--start-date", "not-a-date",
    ])
    assert code == 2
    assert "invalid --start-date" in stdout


def test_seo_report_missing_client_arg(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([
            "seo-report",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_seo_report_writes_audit(tmp_path: Path) -> None:
    code, _ = _run([
        "seo-report",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    audit_root = tmp_path / "mem" / "acme" / "audit"
    assert audit_root.exists()
    content = "\n".join(
        f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl")
    )
    assert "seo_intelligence_report_pack" in content
    assert "built" in content
