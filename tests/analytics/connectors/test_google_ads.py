"""Tests for the Google Ads read-only adapter — entirely mocked.

No real Google Ads SDK call is ever issued. The SDK is *not*
required to be installed for these tests to pass.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.analytics.connectors.google_ads import GoogleAdsReadOnlyConnector


def _make_row(
    *,
    campaign_id: int = 1,
    campaign_name: str = "Brand Search",
    ad_group_id: int = 100,
    ad_group_name: str = "Exact Match",
    impressions: int = 1000,
    clicks: int = 50,
    cost_micros: int = 25_000_000,  # $25
    conversions: float = 3.0,
    ctr: float = 0.05,
    average_cpc: float = 500_000.0,
    conversions_value: float = 150.0,
    cost_per_conversion: float = 8.0,
    segments_date: str = "2026-05-15",
):
    """Build a SimpleNamespace mimicking the proto-plus row shape."""
    return SimpleNamespace(
        campaign=SimpleNamespace(
            id=campaign_id,
            name=campaign_name,
            status=SimpleNamespace(name="ENABLED"),
        ),
        ad_group=SimpleNamespace(
            id=ad_group_id,
            name=ad_group_name,
            status=SimpleNamespace(name="ENABLED"),
        ),
        segments=SimpleNamespace(date=segments_date),
        metrics=SimpleNamespace(
            impressions=impressions,
            clicks=clicks,
            cost_micros=cost_micros,
            conversions=conversions,
            ctr=ctr,
            average_cpc=average_cpc,
            conversions_value=conversions_value,
            cost_per_conversion=cost_per_conversion,
        ),
    )


def _make_client(rows: list):
    """Build a fake GoogleAdsClient whose ``GoogleAdsService.search_stream``
    yields one batch with the given rows."""

    def search_stream(*, customer_id, query):
        del customer_id, query  # unused in the fake
        return iter([SimpleNamespace(results=rows)])

    service = SimpleNamespace(search_stream=search_stream)
    return SimpleNamespace(get_service=lambda name: service)


# ---------- availability ----------


def test_availability_skipped_without_any_env() -> None:
    c = GoogleAdsReadOnlyConnector(env={})
    av = c.availability()
    assert av.credentials_available is False
    assert "GOOGLE_ADS_DEVELOPER_TOKEN" in av.reason
    assert "GOOGLE_ADS_CUSTOMER_ID" in av.reason


def test_availability_skipped_with_partial_env() -> None:
    c = GoogleAdsReadOnlyConnector(env={
        "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token",
        "GOOGLE_ADS_CLIENT_ID": "cid",
        # client_secret, refresh_token, customer_id missing
    })
    av = c.availability()
    assert av.credentials_available is False
    assert "GOOGLE_ADS_CLIENT_SECRET" in av.reason
    assert "GOOGLE_ADS_REFRESH_TOKEN" in av.reason
    assert "GOOGLE_ADS_CUSTOMER_ID" in av.reason


def test_availability_login_customer_id_is_optional() -> None:
    """Missing ``GOOGLE_ADS_LOGIN_CUSTOMER_ID`` must NOT mark the
    connector unavailable (it is only required for MCC accounts)."""
    env = {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "tok",
        "GOOGLE_ADS_CLIENT_ID": "cid",
        "GOOGLE_ADS_CLIENT_SECRET": "csec",
        "GOOGLE_ADS_REFRESH_TOKEN": "rtok",
        "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
    }
    c = GoogleAdsReadOnlyConnector(env=env)
    av = c.availability()
    # SDK is not installed in CI, so credentials_available is True
    # but is_ready stays False because sdk_available is False.
    assert av.credentials_available is True
    assert av.sdk_available is False
    assert "google-ads SDK not installed" in av.reason


# ---------- fetch ----------


def test_fetch_returns_empty_without_customer_id() -> None:
    # Defensive guard: even bypassing availability(), fetch must
    # not crash when GOOGLE_ADS_CUSTOMER_ID is empty.
    c = GoogleAdsReadOnlyConnector(env={})
    result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))
    assert result.rows == []
    assert result.identifier is None


def test_fetch_calls_search_stream_only_and_returns_rows() -> None:
    """Pin: the connector calls ``GoogleAdsService.search_stream``
    via ``get_service('GoogleAdsService')``. No other service name
    is requested."""
    env = {"GOOGLE_ADS_CUSTOMER_ID": "1234567890"}
    c = GoogleAdsReadOnlyConnector(env=env)
    rows = [_make_row(), _make_row(ad_group_id=101, ad_group_name="Broad Match")]
    fake_client = _make_client(rows)

    requested_services: list[str] = []
    original_get = fake_client.get_service

    def tracking_get_service(name: str):
        requested_services.append(name)
        return original_get(name)

    fake_client.get_service = tracking_get_service

    with patch.object(
        GoogleAdsReadOnlyConnector, "_build_client", return_value=fake_client,
    ):
        result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))

    assert result.identifier == "1234567890"
    assert len(result.rows) == 2
    # The only service the connector asks for is the read service.
    assert requested_services == ["GoogleAdsService"]
    # Spot-check one row was flattened correctly.
    r = result.rows[0]
    assert r["campaign.name"] == "Brand Search"
    assert r["ad_group.name"] == "Exact Match"
    assert r["metrics.impressions"] == 1000
    assert r["metrics.cost_micros"] == 25_000_000
    assert r["segments.date"] == "2026-05-15"


def test_fetch_handles_multiple_batches() -> None:
    env = {"GOOGLE_ADS_CUSTOMER_ID": "999"}
    c = GoogleAdsReadOnlyConnector(env=env)

    rows_a = [_make_row(campaign_name="A1"), _make_row(campaign_name="A2")]
    rows_b = [_make_row(campaign_name="B1")]

    def search_stream(*, customer_id, query):
        del customer_id, query
        return iter([
            SimpleNamespace(results=rows_a),
            SimpleNamespace(results=rows_b),
        ])

    fake_client = SimpleNamespace(
        get_service=lambda name: SimpleNamespace(search_stream=search_stream),
    )
    with patch.object(
        GoogleAdsReadOnlyConnector, "_build_client", return_value=fake_client,
    ):
        result = c.fetch(start_date=date(2026, 5, 1), end_date=date(2026, 5, 28))
    assert len(result.rows) == 3


def test_fake_client_has_no_mutate_service() -> None:
    """If anyone tried to call a mutation service, the fake client
    used by tests intentionally has no such method — AttributeError
    would surface immediately."""
    fake = _make_client([])
    service = fake.get_service("GoogleAdsService")
    assert callable(service.search_stream)
    # Verify the service object exposes only the read entry point.
    for forbidden in (
        "mutate_campaigns", "mutate_ad_groups", "mutate_ads",
        "mutate_keywords", "mutate_campaign_budgets",
    ):
        assert not hasattr(service, forbidden)
