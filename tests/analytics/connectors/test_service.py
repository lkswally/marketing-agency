"""Tests for AnalyticsFetchService — end-to-end with fake connectors."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.analytics.connectors import (
    AnalyticsFetchService,
    DryRunConnector,
    FetchStatus,
    resolve_connector,
)
from core.analytics.connectors.base import (
    AnalyticsConnector,
    ConnectorAvailability,
    FetchResult,
)
from core.analytics.connectors.service import (
    fetch_and_persist,
    fingerprint_identifier,
    render_markdown_fetch_report,
    write_report_outputs,
)
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricsSnapshot,
)
from core.memory import JsonFileMemory


class _FakeConnector(AnalyticsConnector):
    def __init__(
        self,
        source: str,
        *,
        rows: list[dict] | None = None,
        availability_ok: bool = True,
        reason: str = "ok",
        raise_on_fetch: Exception | None = None,
        identifier: str | None = "fake-identifier-1234567890",
    ) -> None:
        self._source = source
        self._rows = rows or []
        self._availability_ok = availability_ok
        self._reason = reason
        self._raise = raise_on_fetch
        self._identifier = identifier

    @property
    def source(self) -> str:
        return self._source

    def availability(self) -> ConnectorAvailability:
        return ConnectorAvailability(
            sdk_available=self._availability_ok,
            credentials_available=self._availability_ok,
            reason=self._reason,
        )

    def fetch(self, *, start_date: date, end_date: date) -> FetchResult:
        if self._raise is not None:
            raise self._raise
        return FetchResult(rows=self._rows, identifier=self._identifier)


# ---------- resolve_connector ----------


def test_resolve_connector_unknown_source_raises() -> None:
    with pytest.raises(ValueError, match="unsupported source"):
        resolve_connector("googleads")


def test_resolve_connector_dry_run_returns_dry_run_connector() -> None:
    c = resolve_connector("ga4", dry_run=True)
    assert isinstance(c, DryRunConnector)
    assert c.source == "ga4"


# ---------- fingerprint ----------


def test_fingerprint_is_short_and_deterministic() -> None:
    fp1 = fingerprint_identifier("properties/12345")
    fp2 = fingerprint_identifier("properties/12345")
    assert fp1 == fp2
    assert fp1 is not None
    assert len(fp1) == 8


def test_fingerprint_handles_none() -> None:
    assert fingerprint_identifier(None) is None
    assert fingerprint_identifier("") is None


# ---------- skipped paths ----------


def test_fetch_skipped_when_connector_unavailable(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", availability_ok=False, reason="missing env X")
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    assert report.status is FetchStatus.SKIPPED
    assert report.rows_fetched == 0
    assert report.rows_normalized == 0
    assert report.snapshot_id is None
    assert report.reason == "missing env X"
    assert report.sdk_available is False
    assert report.credentials_available is False

    # No snapshot was created since no rows were appended.
    from core.memory import EntityNotFound
    with pytest.raises(EntityNotFound):
        mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)


def test_fetch_skipped_when_dry_run(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    report = fetch_and_persist(
        mem, client_slug="acme", source="ga4", dry_run=True,
    )
    assert report.status is FetchStatus.SKIPPED
    assert report.dry_run is True
    assert "dry-run" in (report.reason or "")


# ---------- failed path ----------


def test_fetch_failed_when_connector_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector(
        "ga4", raise_on_fetch=RuntimeError("transient quota error"),
    )
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    assert report.status is FetchStatus.FAILED
    assert report.rows_fetched == 0
    # Reason carries the exception type but NOT the message (no
    # accidental URL / identifier leakage).
    assert "RuntimeError" in (report.reason or "")
    assert "transient quota error" not in (report.reason or "")


# ---------- ok / partial ----------


def _ga4_row(**overrides) -> dict:
    base = {
        "date": "20260515",
        "sessionDefaultChannelGroup": "Organic Search",
        "pagePath": "/blog/x",
        "sessions": "120",
        "totalUsers": "100",
        "conversions": "5",
        "bounceRate": "0.42",
    }
    base.update(overrides)
    return base


def test_fetch_ok_appends_to_snapshot(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", rows=[_ga4_row(), _ga4_row(pagePath="/blog/y")])
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    assert report.status is FetchStatus.OK
    assert report.rows_fetched == 2
    assert report.rows_normalized == 8  # 2 rows * 4 metrics each
    assert report.snapshot_id is not None
    assert report.identifier_fingerprint is not None
    # The fingerprint is 8 hex chars and NOT the raw identifier.
    assert report.identifier_fingerprint != "fake-identifier-1234567890"
    assert len(report.identifier_fingerprint) == 8

    raw = mem.get("acme", METRICS_SNAPSHOT_KIND, SINGLETON_ID)
    snap = MetricsSnapshot.model_validate(raw)
    assert snap.total_rows == 8


def test_fetch_partial_when_some_rows_invalid(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    # Second row has no numeric metric — normaliser rejects it.
    bad_row = {"date": "20260515", "sessionDefaultChannelGroup": "Direct"}
    fake = _FakeConnector("ga4", rows=[_ga4_row(), bad_row])
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    assert report.status is FetchStatus.PARTIAL
    assert report.rows_fetched == 2
    assert report.rows_normalized == 4
    assert report.rows_rejected == 1


def test_fetch_search_console_ok(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    rows = [
        {"date": "2026-05-15", "query": "x", "page": "/p",
         "clicks": 10, "impressions": 1000, "ctr": 0.01, "position": 12.4},
    ]
    fake = _FakeConnector("search_console", rows=rows)
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    assert report.status is FetchStatus.OK
    assert report.rows_normalized == 4


# ---------- audit + persistence ----------


def test_audit_records_fetch_event(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", rows=[_ga4_row()])
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")

    events = list(mem.read_audit_events("acme"))
    assert any(
        "analytics_fetch" in e.payload
        and e.payload["analytics_fetch"]["action"] == "fetch_ok"
        and e.payload["analytics_fetch"]["report_id"] == report.report_id
        for e in events
    )


def test_audit_records_skipped_event(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", availability_ok=False, reason="missing creds")
    AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    events = list(mem.read_audit_events("acme"))
    actions = [
        e.payload["analytics_fetch"]["action"]
        for e in events
        if "analytics_fetch" in e.payload
    ]
    assert "fetch_skipped" in actions


def test_audit_does_not_carry_raw_identifier(tmp_path: Path) -> None:
    """Pin: the audit event must NEVER contain the raw GA4 property
    id / Search Console site url."""
    mem = JsonFileMemory(tmp_path / "mem")
    secret_id = "properties/SUPER-SECRET-987654"
    fake = _FakeConnector("ga4", rows=[_ga4_row()], identifier=secret_id)
    AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    events = list(mem.read_audit_events("acme"))
    serialised = "\n".join(str(e.model_dump()) for e in events)
    assert "SUPER-SECRET-987654" not in serialised
    assert "properties/" not in serialised


# ---------- renderer + writer ----------


def test_render_markdown_includes_sections(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", rows=[_ga4_row()])
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    md = render_markdown_fetch_report(report)
    assert "Analytics fetch report" in md
    assert "ga4" in md
    assert "Counts" in md
    assert "Read-only" in md


def test_render_markdown_skipped_shows_reason(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", availability_ok=False, reason="missing env X")
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    md = render_markdown_fetch_report(report)
    assert "Reason" in md
    assert "missing env X" in md


def test_write_report_outputs(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", rows=[_ga4_row()])
    report = AnalyticsFetchService(memory=mem, connector=fake).run(client_slug="acme")
    out_dir = tmp_path / "outputs"
    md_path, json_path = write_report_outputs(report, outputs_dir=out_dir)
    assert md_path.exists()
    assert json_path.exists()
    # JSON round-trips.
    import json
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["source"] == "ga4"
    assert payload["status"] == "ok"


# ---------- lookback ----------


def test_service_passes_lookback_to_report(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    fake = _FakeConnector("ga4", rows=[_ga4_row()])
    report = AnalyticsFetchService(
        memory=mem, connector=fake, lookback_days=7,
    ).run(client_slug="acme")
    assert report.lookback_days == 7
