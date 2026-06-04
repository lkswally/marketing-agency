"""Tests for the connector ABC + DryRunConnector + lookback helper."""

from __future__ import annotations

from datetime import date

import pytest

from core.analytics.connectors.base import (
    AVAILABILITY_OK,
    AnalyticsConnector,
    ConnectorAvailability,
    DryRunConnector,
    default_lookback_window,
)


def test_availability_dataclass_is_ready_flag() -> None:
    ok = ConnectorAvailability(
        sdk_available=True, credentials_available=True, reason=AVAILABILITY_OK,
    )
    assert ok.is_ready is True

    missing_creds = ConnectorAvailability(
        sdk_available=True, credentials_available=False, reason="no creds",
    )
    assert missing_creds.is_ready is False


def test_dry_run_connector_reports_unavailable_with_reason() -> None:
    c = DryRunConnector("ga4", reason="dry-run forced")
    av = c.availability()
    assert av.is_ready is False
    assert av.reason == "dry-run forced"
    assert av.sdk_available is False
    assert av.credentials_available is False
    assert c.source == "ga4"


def test_dry_run_connector_fetch_returns_no_rows() -> None:
    c = DryRunConnector("search_console")
    result = c.fetch(start_date=date(2026, 1, 1), end_date=date(2026, 1, 28))
    assert result.rows == []
    assert result.identifier is None
    assert any("dry" in n.lower() for n in result.notes)


def test_default_lookback_window_28_days() -> None:
    today = date(2026, 6, 1)
    start, end = default_lookback_window(today, 28)
    # end is yesterday, start is end - 27 days (so window = 28 days incl)
    assert end == date(2026, 5, 31)
    assert start == date(2026, 5, 4)
    assert (end - start).days == 27


def test_default_lookback_window_rejects_zero() -> None:
    with pytest.raises(ValueError, match="lookback_days"):
        default_lookback_window(date(2026, 6, 1), 0)


def test_abc_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        AnalyticsConnector()  # type: ignore[abstract]


def test_abc_only_declares_read_methods() -> None:
    """Pin: no public write-style method on the ABC."""
    public = {
        name
        for name in dir(AnalyticsConnector)
        if not name.startswith("_")
    }
    forbidden = {
        "create", "update", "delete", "write", "put", "patch", "remove",
        "submit", "insert", "post", "add",
    }
    assert public.isdisjoint(forbidden), public & forbidden
