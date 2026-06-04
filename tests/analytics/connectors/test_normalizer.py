"""Tests for the GA4 / Search Console row normaliser."""

from __future__ import annotations

from datetime import date

from core.analytics.connectors.normalizer import (
    normalize_ga4_rows,
    normalize_google_ads_rows,
    normalize_search_console_rows,
)
from core.analytics.models import MetricSource


def test_ga4_row_produces_one_metric_row_per_metric() -> None:
    rows = [
        {
            "date": "20260515",
            "sessionDefaultChannelGroup": "Organic Search",
            "pagePath": "/blog/x",
            "sessions": "120",
            "totalUsers": "100",
            "conversions": "5",
            "bounceRate": "0.42",
        },
    ]
    out, reasons = normalize_ga4_rows(rows)
    assert reasons == []
    assert len(out) == 4
    names = {r.metric_name for r in out}
    assert names == {"sessions", "users", "conversions", "bounce_rate"}
    for r in out:
        assert r.source is MetricSource.GA4
        assert r.event_date == date(2026, 5, 15)
        assert r.channel == "organic_search"
        assert r.content_ref == "/blog/x"


def test_ga4_handles_dash_separated_date() -> None:
    rows = [{"date": "2026-05-15", "sessions": "10"}]
    out, _ = normalize_ga4_rows(rows)
    assert out and out[0].event_date == date(2026, 5, 15)


def test_ga4_rejects_row_with_no_metric() -> None:
    rows = [{"date": "20260515", "sessionDefaultChannelGroup": "Direct"}]
    out, reasons = normalize_ga4_rows(rows)
    assert out == []
    assert len(reasons) == 1
    assert "no GA4 numeric" in reasons[0]


def test_ga4_skips_non_numeric_values() -> None:
    rows = [
        {
            "date": "20260515",
            "sessions": "not-a-number",
            "totalUsers": "5",
        }
    ]
    out, _ = normalize_ga4_rows(rows)
    assert len(out) == 1
    assert out[0].metric_name == "users"
    assert out[0].value == 5.0


def test_search_console_row_produces_four_metric_rows() -> None:
    rows = [
        {
            "date": "2026-05-20",
            "query": "marketing agency",
            "page": "https://example.com/services",
            "clicks": 10,
            "impressions": 1000,
            "ctr": 0.01,
            "position": 12.4,
        }
    ]
    out, reasons = normalize_search_console_rows(rows)
    assert reasons == []
    assert len(out) == 4
    for r in out:
        assert r.source is MetricSource.SEARCH_CONSOLE
        assert r.event_date == date(2026, 5, 20)
        assert r.channel == "organic_search"
        assert r.query == "marketing agency"
        assert r.content_ref == "https://example.com/services"


def test_search_console_rejects_row_without_metric() -> None:
    rows = [{"date": "2026-05-20", "query": "x", "page": "y"}]
    out, reasons = normalize_search_console_rows(rows)
    assert out == []
    assert "no Search Console numeric" in reasons[0]


def test_ga4_slugify_handles_special_characters() -> None:
    rows = [
        {
            "date": "20260601",
            "sessionDefaultChannelGroup": "Paid Search/Brand",
            "sessions": "1",
        }
    ]
    out, _ = normalize_ga4_rows(rows)
    assert out[0].channel == "paid_search_brand"


def test_google_ads_row_produces_one_row_per_metric() -> None:
    rows = [
        {
            "campaign.id": "1",
            "campaign.name": "Brand Search",
            "ad_group.id": "100",
            "ad_group.name": "Exact Match",
            "segments.date": "2026-05-15",
            "metrics.impressions": 1000,
            "metrics.clicks": 50,
            "metrics.cost_micros": 25_000_000,  # $25
            "metrics.conversions": 3.0,
            "metrics.ctr": 0.05,
            "metrics.average_cpc": 500_000.0,
            "metrics.conversions_value": 150.0,
            "metrics.cost_per_conversion": 8.0,
        }
    ]
    out, reasons = normalize_google_ads_rows(rows)
    assert reasons == []
    assert len(out) == 8
    for r in out:
        assert r.source is MetricSource.GOOGLE_ADS
        assert r.event_date == date(2026, 5, 15)
        assert r.channel == "google_ads"
        assert r.content_ref == "campaign:1::ad_group:100"
        assert r.dimension == "Brand Search / Exact Match"

    by_name = {r.metric_name: r.value for r in out}
    # Cost is divided by 1_000_000 from micros to whole units.
    assert by_name["cost"] == 25.0
    assert by_name["impressions"] == 1000.0
    assert by_name["clicks"] == 50.0
    assert by_name["conversions"] == 3.0
    assert by_name["ctr"] == 0.05
    assert by_name["cpc"] == 500_000.0
    assert by_name["cpa"] == 8.0


def test_google_ads_rejects_row_with_no_identifiers() -> None:
    rows = [{"segments.date": "2026-05-15", "metrics.clicks": 10}]
    out, reasons = normalize_google_ads_rows(rows)
    assert out == []
    assert "missing campaign.id" in reasons[0]


def test_google_ads_rejects_row_with_no_metric() -> None:
    rows = [{
        "campaign.id": "1", "campaign.name": "X",
        "ad_group.id": "2", "ad_group.name": "Y",
        "segments.date": "2026-05-15",
    }]
    out, reasons = normalize_google_ads_rows(rows)
    assert out == []
    assert "no Google Ads numeric metric" in reasons[0]


def test_google_ads_skips_non_numeric_values() -> None:
    rows = [{
        "campaign.id": "1",
        "ad_group.id": "100",
        "segments.date": "2026-05-15",
        "metrics.impressions": "not-a-number",
        "metrics.clicks": 5,
    }]
    out, _ = normalize_google_ads_rows(rows)
    assert len(out) == 1
    assert out[0].metric_name == "clicks"
    assert out[0].value == 5.0


def test_google_ads_partial_dimension_when_campaign_name_only() -> None:
    rows = [{
        "campaign.id": "1", "campaign.name": "Brand",
        "ad_group.id": "100", "ad_group.name": "",
        "metrics.clicks": 5,
    }]
    out, _ = normalize_google_ads_rows(rows)
    assert out[0].dimension == "Brand"


def test_search_console_percent_string_parsed() -> None:
    rows = [
        {
            "date": "2026-05-20",
            "query": "x",
            "page": "y",
            "ctr": "3.5%",
            "impressions": "1,234",
        }
    ]
    out, _ = normalize_search_console_rows(rows)
    by_name = {r.metric_name: r.value for r in out}
    assert by_name["ctr"] == 0.035
    assert by_name["impressions"] == 1234.0
