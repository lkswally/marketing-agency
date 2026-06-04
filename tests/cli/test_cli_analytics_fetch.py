"""CLI tests for ``mkt analytics-fetch``.

All tests run with no Google SDK / credentials, exercising the
skipped / dry-run paths plus argparse error handling. No real
upstream call is ever issued.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from cli.main import main


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


@pytest.fixture(autouse=True)
def _scrub_google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure no real Google env vars leak from the host env."""
    for k in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GA4_PROPERTY_ID",
        "SEARCH_CONSOLE_SITE_URL",
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        "GOOGLE_ADS_CUSTOMER_ID",
    ):
        monkeypatch.delenv(k, raising=False)


def test_dry_run_ga4_exits_0_with_skipped_status(tmp_path: Path) -> None:
    code, stdout = _run([
        "analytics-fetch",
        "--client", "acme",
        "--source", "ga4",
        "--dry-run",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["status"] == "skipped"
    assert payload["dry_run"] is True
    assert payload["sdk_available"] is False
    assert payload["credentials_available"] is False
    assert payload["rows_normalized"] == 0
    # Markdown and JSON files written.
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["json_path"]).exists()


def test_missing_creds_search_console_exits_0_with_skipped(tmp_path: Path) -> None:
    code, stdout = _run([
        "analytics-fetch",
        "--client", "acme",
        "--source", "search_console",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["status"] == "skipped"
    assert payload["source"] == "search_console"
    # Reason mentions a missing env var (or SDK).
    assert payload["reason"]
    assert payload["reason"].strip() != ""


def test_missing_source_arg_exits_nonzero(tmp_path: Path) -> None:
    # argparse rejects when --source is missing.
    with pytest.raises(SystemExit) as exc:
        _run([
            "analytics-fetch",
            "--client", "acme",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_unsupported_source_rejected_by_argparse(tmp_path: Path) -> None:
    # ``--source googleads`` is rejected by argparse choices=().
    with pytest.raises(SystemExit) as exc:
        _run([
            "analytics-fetch",
            "--client", "acme",
            "--source", "googleads",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_dry_run_writes_audit_event(tmp_path: Path) -> None:
    code, _ = _run([
        "analytics-fetch",
        "--client", "acme",
        "--source", "ga4",
        "--dry-run",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    # Look for the analytics_fetch audit event on disk.
    audit_root = tmp_path / "mem" / "acme" / "audit"
    assert audit_root.exists(), "audit directory should exist"
    jsonl_files = list(audit_root.glob("*.jsonl"))
    assert jsonl_files, "at least one audit JSONL file expected"
    content = "\n".join(f.read_text(encoding="utf-8") for f in jsonl_files)
    assert "analytics_fetch" in content
    assert "fetch_skipped" in content


def test_dry_run_report_does_not_leak_env_keys(tmp_path: Path) -> None:
    """Even if the user has the env vars set, dry-run skips the
    upstream call. We test the rendered Markdown does not echo
    any of the env vars' raw values."""
    monkeyenv = {
        "GOOGLE_APPLICATION_CREDENTIALS": "/fake/path/SECRET-creds.json",
        "GA4_PROPERTY_ID": "PROP-987654321",
    }
    saved = {k: os.environ.get(k) for k in monkeyenv}
    try:
        os.environ.update(monkeyenv)
        code, stdout = _run([
            "analytics-fetch",
            "--client", "acme",
            "--source", "ga4",
            "--dry-run",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ])
        assert code == 0
        payload = json.loads(stdout)
        md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
        assert "SECRET-creds.json" not in md
        assert "PROP-987654321" not in md
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_dry_run_google_ads_exits_0_with_skipped(tmp_path: Path) -> None:
    code, stdout = _run([
        "analytics-fetch",
        "--client", "acme",
        "--source", "google_ads",
        "--dry-run",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["status"] == "skipped"
    assert payload["source"] == "google_ads"
    assert payload["dry_run"] is True


def test_missing_creds_google_ads_skips(tmp_path: Path) -> None:
    code, stdout = _run([
        "analytics-fetch",
        "--client", "acme",
        "--source", "google_ads",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["status"] == "skipped"
    # The reason mentions at least one missing env var.
    assert "GOOGLE_ADS_DEVELOPER_TOKEN" in (payload["reason"] or "")


def test_lookback_days_flag_passed_through(tmp_path: Path) -> None:
    code, stdout = _run([
        "analytics-fetch",
        "--client", "acme",
        "--source", "ga4",
        "--dry-run",
        "--lookback-days", "7",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["lookback_days"] == 7
