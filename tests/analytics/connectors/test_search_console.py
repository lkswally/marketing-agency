"""Tests for the Search Console read-only adapter — entirely mocked."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.analytics.connectors.search_console import (
    SearchConsoleReadOnlyConnector,
)


def _make_service(rows: list[dict]):
    """Build a fake service with exactly the read chain we use."""
    response = {"rows": rows}
    query_obj = SimpleNamespace(execute=lambda: response)
    analytics = SimpleNamespace(query=lambda siteUrl, body: query_obj)  # noqa: N803
    return SimpleNamespace(searchanalytics=lambda: analytics)


def test_availability_skipped_without_creds() -> None:
    c = SearchConsoleReadOnlyConnector(env={})
    av = c.availability()
    assert av.credentials_available is False
    assert "GOOGLE_APPLICATION_CREDENTIALS" in av.reason


def test_availability_skipped_without_site_url(tmp_path) -> None:
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    c = SearchConsoleReadOnlyConnector(env={
        "GOOGLE_APPLICATION_CREDENTIALS": str(creds),
    })
    av = c.availability()
    assert av.credentials_available is False
    assert "SEARCH_CONSOLE_SITE_URL" in av.reason


def test_fetch_returns_empty_without_site_url() -> None:
    c = SearchConsoleReadOnlyConnector(env={})
    result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))
    assert result.rows == []
    assert result.identifier is None


def test_fetch_uses_searchanalytics_query_only() -> None:
    site = "https://example.com/"
    c = SearchConsoleReadOnlyConnector(env={"SEARCH_CONSOLE_SITE_URL": site})
    sample = [
        {"keys": ["2026-05-15", "marketing agency", "/services"],
         "clicks": 10, "impressions": 1000, "ctr": 0.01, "position": 12.4},
    ]
    fake_service = _make_service(sample)
    with patch.object(
        SearchConsoleReadOnlyConnector, "_build_service", return_value=fake_service,
    ):
        result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))

    assert result.identifier == site
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["date"] == "2026-05-15"
    assert row["query"] == "marketing agency"
    assert row["page"] == "/services"
    assert row["clicks"] == 10
    assert row["impressions"] == 1000


def test_fake_service_only_has_searchanalytics() -> None:
    """The fake service exposes ``searchanalytics`` only. Any attempt
    to invoke ``sitemaps`` / ``sites`` mutation methods would
    AttributeError immediately."""
    fake = _make_service([])
    assert callable(fake.searchanalytics)
    for forbidden in ("sitemaps", "sites_add", "sites_delete"):
        assert not hasattr(fake, forbidden)


def test_request_body_carries_query_dimensions_only() -> None:
    c = SearchConsoleReadOnlyConnector()
    body = c._build_request_body(
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 28),
    )
    assert body["dimensions"] == ["date", "query", "page"]
    assert body["startDate"] == "2026-05-01"
    assert body["endDate"] == "2026-05-28"
    assert body["rowLimit"] == 1000
