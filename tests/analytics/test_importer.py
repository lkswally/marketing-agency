"""AnalyticsImporter tests — per-source parsing + persistence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from core.analytics import (
    ANALYTICS_IMPORT_REPORT_KIND,
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    AnalyticsImporter,
    ImporterError,
    MetricSource,
)
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    text = ",".join(header) + "\n" + "\n".join(",".join(r) for r in rows) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


# ---------- Files ----------

def test_missing_file_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ImporterError):
        AnalyticsImporter(memory=mem).import_file(
            client_slug="acme",
            source=MetricSource.MANUAL,
            file_path=tmp_path / "nope.csv",
        )


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    bad = tmp_path / "data.txt"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(ImporterError):
        AnalyticsImporter(memory=mem).import_file(
            client_slug="acme",
            source=MetricSource.MANUAL,
            file_path=bad,
        )


def test_invalid_json_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json}", encoding="utf-8")
    with pytest.raises(ImporterError):
        AnalyticsImporter(memory=mem).import_file(
            client_slug="acme",
            source=MetricSource.MANUAL,
            file_path=bad,
        )


# ---------- Per-source parsing ----------

def test_ga4_csv_one_row_produces_multiple_metric_rows(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "ga4.csv",
        ["date", "channel", "page", "sessions", "users", "conversions", "bounce_rate"],
        [["2026-05-01", "organic_search", "/blog/x", "420", "310", "12", "0.42"]],
    )
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.GA4, file_path=f,
    )
    # 4 metrics × 1 row = 4 metric rows.
    assert report.rows_imported == 4
    assert snapshot.total_rows == 4
    metrics = {r.metric_name for r in snapshot.rows}
    assert metrics == {"sessions", "users", "conversions", "bounce_rate"}
    for r in snapshot.rows:
        assert r.event_date == date(2026, 5, 1)
        assert r.channel == "organic_search"


def test_search_console_csv(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "sc.csv",
        ["date", "page", "query", "clicks", "impressions", "ctr", "position"],
        [["2026-05-01", "/blog/x", "marketing pipeline", "40", "2000", "2.0%", "11"]],
    )
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.SEARCH_CONSOLE, file_path=f,
    )
    assert report.rows_imported == 4
    ctr_row = next(r for r in snapshot.rows if r.metric_name == "ctr")
    assert ctr_row.value == pytest.approx(0.02)
    pos_row = next(r for r in snapshot.rows if r.metric_name == "position")
    assert pos_row.value == 11.0
    # Query and page are preserved.
    assert all(r.query == "marketing pipeline" for r in snapshot.rows)


def test_social_csv_requires_channel(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "social.csv",
        ["date", "channel", "post_id", "impressions", "engagement", "clicks", "reach"],
        [
            ["2026-05-01", "linkedin", "post-1", "8000", "420", "180", "7200"],
            ["2026-05-02", "", "post-2", "100", "10", "1", "90"],  # missing channel
        ],
    )
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.SOCIAL, file_path=f,
    )
    # First row → 4 metrics, second row rejected.
    assert report.rows_imported == 4
    assert report.rows_rejected == 1
    assert "missing channel" in report.rejected_reasons[0]


def test_email_csv_requires_campaign_id(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "email.csv",
        ["date", "campaign_id", "sent", "opens", "clicks", "unsubscribes"],
        [
            ["2026-05-01", "email-1", "1200", "340", "72", "3"],
            ["2026-05-02", "", "100", "10", "1", "0"],  # missing campaign_id
        ],
    )
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.EMAIL, file_path=f,
    )
    assert report.rows_imported == 4
    assert report.rows_rejected == 1


def test_manual_csv(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "manual.csv",
        ["date", "channel", "metric_name", "value", "content_ref", "dimension"],
        [
            ["2026-05-01", "podcast", "downloads", "1200", "episode-12", "youtube"],
            ["2026-05-02", "podcast", "downloads", "abc", "ep-13", ""],  # unparseable
            ["2026-05-03", "podcast", "", "100", "ep-14", ""],  # missing metric_name
        ],
    )
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.MANUAL, file_path=f,
    )
    assert report.rows_imported == 1
    assert report.rows_rejected == 2


def test_json_array_works(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = tmp_path / "data.json"
    f.write_text(json.dumps([
        {"date": "2026-05-01", "channel": "linkedin", "post_id": "p1",
         "impressions": 1000, "engagement": 50, "clicks": 10, "reach": 900},
    ]), encoding="utf-8")
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.SOCIAL, file_path=f,
    )
    assert report.rows_imported == 4


def test_json_with_rows_wrapper(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = tmp_path / "wrapped.json"
    f.write_text(json.dumps({"meta": {"x": 1}, "rows": [
        {"date": "2026-05-01", "campaign_id": "e1", "sent": 100, "opens": 20,
         "clicks": 5, "unsubscribes": 0},
    ]}), encoding="utf-8")
    report, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.EMAIL, file_path=f,
    )
    assert report.rows_imported == 4


# ---------- Number parsing ----------

def test_percent_coercion(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "sc.csv",
        ["date", "page", "query", "clicks", "impressions", "ctr", "position"],
        [["2026-05-01", "/x", "q", "10", "1000", "1.0%", "5"]],
    )
    _, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.SEARCH_CONSOLE, file_path=f,
    )
    ctr = next(r for r in snapshot.rows if r.metric_name == "ctr")
    assert ctr.value == pytest.approx(0.01)


def test_comma_separator_coercion(tmp_path: Path) -> None:
    """Comma-separated numbers (``"1,234"``) require proper CSV quoting
    to survive the split. The importer then strips the comma."""
    mem = JsonFileMemory(tmp_path / "mem")
    f = tmp_path / "ga4.csv"
    # Hand-quoted CSV so "1,234" stays one field.
    f.write_text(
        'date,channel,page,sessions\n2026-05-01,organic_search,/x,"1,234"\n',
        encoding="utf-8",
    )
    _, snapshot = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.GA4, file_path=f,
    )
    assert snapshot.rows[0].value == 1234.0


# ---------- Persistence + audit ----------

def test_imports_append_across_calls(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f1 = _write_csv(
        tmp_path / "ga4_1.csv", ["date", "channel", "page", "sessions"],
        [["2026-05-01", "organic_search", "/x", "100"]],
    )
    f2 = _write_csv(
        tmp_path / "ga4_2.csv", ["date", "channel", "page", "sessions"],
        [["2026-05-02", "organic_search", "/x", "200"]],
    )
    AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.GA4, file_path=f1,
    )
    AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.GA4, file_path=f2,
    )
    raw = mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)
    from core.analytics import MetricsSnapshot
    snapshot = MetricsSnapshot.model_validate(raw)
    assert snapshot.total_rows == 2


def test_import_emits_audit_event(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "ga4.csv", ["date", "channel", "page", "sessions"],
        [["2026-05-01", "organic_search", "/x", "100"]],
    )
    AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.GA4, file_path=f,
    )
    events = mem.read_audit_events("acme")
    actions = [
        e.payload.get("analytics_import", {}).get("action")
        for e in events
        if "analytics_import" in e.payload
    ]
    assert "imported" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []


def test_report_persisted(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    f = _write_csv(
        tmp_path / "ga4.csv", ["date", "channel", "page", "sessions"],
        [["2026-05-01", "organic_search", "/x", "100"]],
    )
    report, _ = AnalyticsImporter(memory=mem).import_file(
        client_slug="acme", source=MetricSource.GA4, file_path=f,
    )
    assert mem.exists("acme", ANALYTICS_IMPORT_REPORT_KIND, SINGLETON_ID)
    raw = mem.get("acme", ANALYTICS_IMPORT_REPORT_KIND, SINGLETON_ID)
    assert raw["import_id"] == report.import_id


# ---------- Real fixtures (sanity) ----------

def test_real_fixtures_parse(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    importer = AnalyticsImporter(memory=mem)
    pairs = [
        (FIXTURES / "ga4_demo.csv", MetricSource.GA4),
        (FIXTURES / "sc_demo.csv", MetricSource.SEARCH_CONSOLE),
        (FIXTURES / "social_demo.csv", MetricSource.SOCIAL),
        (FIXTURES / "email_demo.csv", MetricSource.EMAIL),
    ]
    total = 0
    for path, src in pairs:
        report, _ = importer.import_file(
            client_slug="acme", source=src, file_path=path,
        )
        assert report.rows_imported > 0
        total += report.rows_imported
    # Across 4 fixtures we expect more than 30 normalised rows.
    assert total > 30


# ---------- No external service ----------

def test_importer_does_not_import_http_clients() -> None:
    import inspect

    import core.analytics.importer as mod
    src = inspect.getsource(mod)
    for forbidden in (
        "import requests", "import httpx", "urllib.request", "os.environ",
    ):
        assert forbidden not in src
