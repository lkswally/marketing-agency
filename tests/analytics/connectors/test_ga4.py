"""Tests for the GA4 read-only adapter — entirely mocked.

No real Google SDK call is ever issued. The SDK is *not* required
to be installed for these tests to pass.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.analytics.connectors.ga4 import GA4ReadOnlyConnector


def _make_response(rows: list[dict[str, str]]):
    dim_headers = [
        SimpleNamespace(name="date"),
        SimpleNamespace(name="sessionDefaultChannelGroup"),
        SimpleNamespace(name="pagePath"),
    ]
    met_headers = [
        SimpleNamespace(name="sessions"),
        SimpleNamespace(name="totalUsers"),
        SimpleNamespace(name="conversions"),
        SimpleNamespace(name="bounceRate"),
    ]
    sdk_rows = []
    for r in rows:
        sdk_rows.append(SimpleNamespace(
            dimension_values=[
                SimpleNamespace(value=r["date"]),
                SimpleNamespace(value=r["channel"]),
                SimpleNamespace(value=r["page"]),
            ],
            metric_values=[
                SimpleNamespace(value=r["sessions"]),
                SimpleNamespace(value=r["users"]),
                SimpleNamespace(value=r["conversions"]),
                SimpleNamespace(value=r["bounce_rate"]),
            ],
        ))
    return SimpleNamespace(
        dimension_headers=dim_headers,
        metric_headers=met_headers,
        rows=sdk_rows,
    )


def test_availability_skipped_without_credentials() -> None:
    c = GA4ReadOnlyConnector(env={})
    av = c.availability()
    assert av.credentials_available is False
    assert "GOOGLE_APPLICATION_CREDENTIALS" in av.reason


def test_availability_skipped_when_property_missing(tmp_path) -> None:
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    c = GA4ReadOnlyConnector(env={"GOOGLE_APPLICATION_CREDENTIALS": str(creds)})
    av = c.availability()
    assert av.credentials_available is False
    assert "GA4_PROPERTY_ID" in av.reason


def test_availability_skipped_when_creds_path_missing() -> None:
    c = GA4ReadOnlyConnector(env={
        "GOOGLE_APPLICATION_CREDENTIALS": "/does/not/exist.json",
        "GA4_PROPERTY_ID": "12345",
    })
    av = c.availability()
    assert av.credentials_available is False
    assert "does not exist" in av.reason


def test_fetch_returns_empty_when_property_missing() -> None:
    # Defensive guard: even if a caller bypasses availability(),
    # fetch must not blow up when GA4_PROPERTY_ID is empty.
    c = GA4ReadOnlyConnector(env={})
    result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))
    assert result.rows == []
    assert result.identifier is None


def test_fetch_calls_run_report_only_and_returns_rows() -> None:
    """Pin: the connector calls ``run_report`` and nothing else."""

    c = GA4ReadOnlyConnector(env={"GA4_PROPERTY_ID": "999111"})
    sample_rows = [
        {
            "date": "20260515", "channel": "Organic Search", "page": "/blog/x",
            "sessions": "120", "users": "100", "conversions": "5",
            "bounce_rate": "0.42",
        },
    ]
    fake_client = SimpleNamespace(run_report=lambda request: _make_response(sample_rows))

    with patch.object(GA4ReadOnlyConnector, "_build_client", return_value=fake_client), \
         patch.object(
             GA4ReadOnlyConnector,
             "_build_request",
             lambda self, *, property_id, start_date, end_date: {
                 "property": f"properties/{property_id}",
                 "start": start_date.isoformat(),
                 "end": end_date.isoformat(),
             },
         ):
        result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))

    assert result.identifier == "999111"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["date"] == "20260515"
    assert row["sessionDefaultChannelGroup"] == "Organic Search"
    assert row["pagePath"] == "/blog/x"


def test_fake_client_exposes_only_read_method() -> None:
    """If anyone tried to call a write method through this connector,
    the SDK client used by tests intentionally has no such method —
    AttributeError would surface immediately."""
    fake = SimpleNamespace(run_report=lambda request: _make_response([]))
    # Only ``run_report`` is defined; any write attribute raises.
    assert callable(fake.run_report)
    for forbidden in ("create_property", "update_property", "delete_property"):
        assert not hasattr(fake, forbidden)
