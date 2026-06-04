"""Tests for AnalyticsFetchReport model + safety pins."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.analytics.connectors.models import (
    ANALYTICS_FETCH_REPORT_KIND,
    ANALYTICS_FETCH_REPORT_VERSION,
    SUPPORTED_SOURCES,
    AnalyticsFetchReport,
    FetchStatus,
)


def _base(**overrides) -> dict:
    base = dict(
        client_slug="acme",
        source="ga4",
        status=FetchStatus.OK,
        rows_fetched=10,
        rows_normalized=10,
        rows_rejected=0,
        sdk_available=True,
        credentials_available=True,
        lookback_days=28,
        started_at=datetime(2026, 6, 1, 10, tzinfo=UTC),
        finished_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return base


def test_round_trip() -> None:
    r = AnalyticsFetchReport(**_base())
    raw = r.model_dump(mode="json")
    r2 = AnalyticsFetchReport.model_validate(raw)
    assert r2.report_id == r.report_id
    assert r2.contract_version == ANALYTICS_FETCH_REPORT_VERSION


def test_supported_sources_constant() -> None:
    assert SUPPORTED_SOURCES == ("ga4", "search_console")


def test_report_kind_constant() -> None:
    assert ANALYTICS_FETCH_REPORT_KIND == "analytics_fetch_report"


def test_rejects_unsupported_source() -> None:
    with pytest.raises(ValueError, match="unsupported source"):
        AnalyticsFetchReport(**_base(source="googleads"))


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AnalyticsFetchReport(**_base(started_at=datetime(2026, 6, 1)))


def test_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError, match="slug"):
        AnalyticsFetchReport(**_base(client_slug="UPPER"))


def test_rejects_negative_counts() -> None:
    with pytest.raises(ValueError):
        AnalyticsFetchReport(**_base(rows_fetched=-1))


def test_rejects_lookback_outside_bounds() -> None:
    with pytest.raises(ValueError):
        AnalyticsFetchReport(**_base(lookback_days=0))
    with pytest.raises(ValueError):
        AnalyticsFetchReport(**_base(lookback_days=400))


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValueError):
        AnalyticsFetchReport(**_base(secret_token="should-not-fit"))


def test_status_enum_values() -> None:
    assert {s.value for s in FetchStatus} == {"ok", "skipped", "partial", "failed"}


def test_skipped_report_has_no_snapshot_id() -> None:
    r = AnalyticsFetchReport(**_base(
        status=FetchStatus.SKIPPED,
        rows_fetched=0,
        rows_normalized=0,
        rows_rejected=0,
        snapshot_id=None,
        reason="missing env GA4_PROPERTY_ID",
        credentials_available=False,
    ))
    assert r.snapshot_id is None
    assert r.reason == "missing env GA4_PROPERTY_ID"


def test_no_credential_fields_on_model() -> None:
    """Pin: the report must not carry token / api_key / secret /
    credential / url / webhook_url fields."""
    forbidden = {"token", "api_key", "secret", "credential", "url", "webhook_url"}
    declared = set(AnalyticsFetchReport.model_fields.keys())
    assert declared.isdisjoint(forbidden), declared & forbidden


def test_identifier_fingerprint_is_short() -> None:
    r = AnalyticsFetchReport(**_base(identifier_fingerprint="abcdef12"))
    assert len(r.identifier_fingerprint or "") <= 32
