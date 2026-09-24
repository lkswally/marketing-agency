"""Tests for the analytics connector fetch application service
(architecture/application-service-boundary, batch 2).

No real external API call — every test exercises the SKIPPED (missing
credentials/SDK) or forced dry-run path, exactly like the pre-existing
CLI tests this service now backs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.analytics_fetch import fetch_analytics
from core.memory import JsonFileMemory


def _ctx(tmp_path: Path, client: str = "acme") -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )


@pytest.fixture(autouse=True)
def _scrub_google_env(monkeypatch: pytest.MonkeyPatch) -> None:
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


# ---------- provider unavailable / missing credentials -> SKIPPED, still OK ----------

def test_dry_run_ga4_is_ok_result_with_skipped_status(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = fetch_analytics(ctx, source="ga4", dry_run=True)
    assert result.ok  # SKIPPED is a successful, structured outcome, not an error
    assert result.data.status.value == "skipped"
    assert result.data.dry_run is True
    assert result.data.sdk_available is False
    assert result.data.credentials_available is False
    assert len(result.artifacts) == 2
    for artifact in result.artifacts:
        assert artifact.path.exists()


def test_missing_creds_search_console_is_ok_with_skipped(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = fetch_analytics(ctx, source="search_console")
    assert result.ok
    assert result.data.status.value == "skipped"
    assert result.data.reason


def test_missing_creds_google_ads_is_ok_with_skipped(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = fetch_analytics(ctx, source="google_ads")
    assert result.ok
    assert result.data.status.value == "skipped"
    assert "GOOGLE_ADS_DEVELOPER_TOKEN" in (result.data.reason or "")


# ---------- connector exception -> FAILED, still OK (not an OperationResult error) ----------

def test_connector_exception_is_ok_with_failed_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connector that IS available but raises during fetch() must
    degrade to FetchStatus.FAILED, never propagate or become an
    OperationResult error — matches the CLI's long-standing contract."""
    from core.analytics.connectors.base import ConnectorAvailability

    class _BoomConnector:
        source = "ga4"

        def availability(self) -> ConnectorAvailability:
            return ConnectorAvailability(
                sdk_available=True, credentials_available=True, reason="ok",
            )

        def fetch(self, *, start_date, end_date):
            raise RuntimeError("simulated upstream failure")

    monkeypatch.setattr(
        "core.application.services.analytics_fetch.resolve_connector",
        lambda source, *, dry_run=False: _BoomConnector(),
    )
    ctx = _ctx(tmp_path)
    result = fetch_analytics(ctx, source="ga4")
    assert result.ok
    assert result.data.status.value == "failed"
    assert "RuntimeError" in (result.data.reason or "")


# ---------- unsupported source -> real ERROR ----------

def test_unsupported_source_is_an_error(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = fetch_analytics(ctx, source="not-a-real-source")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


# ---------- lookback_days passthrough ----------

def test_lookback_days_passed_through(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = fetch_analytics(ctx, source="ga4", dry_run=True, lookback_days=7)
    assert result.data.lookback_days == 7


# ---------- persistence + audit ----------

def test_dry_run_writes_audit_event(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    fetch_analytics(ctx, source="ga4", dry_run=True)
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme")
    fetch_events = [e for e in events if "analytics_fetch" in e.payload]
    assert len(fetch_events) == 1
    assert fetch_events[0].payload["analytics_fetch"]["action"] == "fetch_skipped"


# ---------- secrets boundary (Phase 5/10) ----------

def test_no_secrets_in_result_or_audit_or_artifacts(tmp_path: Path) -> None:
    """Even with real-looking env values present, nothing derived from
    them (OperationResult.data, the persisted audit event, or the
    written Markdown/JSON artifacts) may contain the raw values — only
    booleans and a fingerprint are allowed to cross this boundary."""
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/fake/path/SECRET-creds.json"
    os.environ["GA4_PROPERTY_ID"] = "PROP-987654321"
    try:
        ctx = _ctx(tmp_path)
        result = fetch_analytics(ctx, source="ga4", dry_run=True)
    finally:
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        del os.environ["GA4_PROPERTY_ID"]

    assert result.ok
    result_blob = result.data.to_json()
    assert "SECRET-creds.json" not in result_blob
    assert "PROP-987654321" not in result_blob

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme")
    for e in events:
        blob = e.to_json()
        assert "SECRET-creds.json" not in blob
        assert "PROP-987654321" not in blob

    for artifact in result.artifacts:
        content = artifact.path.read_text(encoding="utf-8")
        assert "SECRET-creds.json" not in content
        assert "PROP-987654321" not in content
