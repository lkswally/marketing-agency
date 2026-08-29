"""Tests for core.intelligence.adapters (MKT-10X dry-run connectors)."""

from datetime import date

from core.intelligence.adapters import (
    DryRunCompetitorMonitor,
    DryRunIntelligenceConnector,
    DryRunMetaAdsConnector,
    DryRunRedditConnector,
    DryRunTrendsConnector,
    DryRunYouTubeConnector,
    IntelligenceAvailability,
    IntelligenceFetchResult,
)
from core.intelligence.adapters.base import IntelligenceConnector

_DATE_RANGE = {"start_date": date(2024, 1, 1), "end_date": date(2024, 1, 31)}


# ---------------------------------------------------------------------------
# Base / ABC contract
# ---------------------------------------------------------------------------


class TestDryRunIntelligenceConnector:
    def test_is_connector(self):
        c = DryRunIntelligenceConnector("test_source")
        assert isinstance(c, IntelligenceConnector)

    def test_availability_always_false(self):
        c = DryRunIntelligenceConnector("test_source")
        avail = c.availability()
        assert isinstance(avail, IntelligenceAvailability)
        assert avail.is_ready is False
        assert avail.sdk_available is False
        assert avail.credentials_available is False

    def test_fetch_returns_empty(self):
        c = DryRunIntelligenceConnector("test_source")
        result = c.fetch(keywords=["foo"], **_DATE_RANGE)
        assert isinstance(result, IntelligenceFetchResult)
        assert result.rows == []
        assert result.source == "test_source"

    def test_custom_reason(self):
        c = DryRunIntelligenceConnector("src", reason="no api key")
        assert "no api key" in c.availability().reason


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


class TestDryRunTrendsConnector:
    def test_source_name(self):
        c = DryRunTrendsConnector()
        assert c.source == "google_trends"

    def test_not_ready(self):
        assert DryRunTrendsConnector().availability().is_ready is False

    def test_fetch_returns_fixture_rows(self):
        c = DryRunTrendsConnector()
        result = c.fetch(keywords=[], **_DATE_RANGE)
        assert len(result.rows) >= 1
        row = result.rows[0]
        assert "keyword" in row
        assert "direction" in row
        assert row["direction"] in ("rising", "falling", "stable")

    def test_fetch_filters_by_keyword(self):
        c = DryRunTrendsConnector()
        result = c.fetch(keywords=["marketing automation"], **_DATE_RANGE)
        assert any(r["keyword"] == "marketing automation" for r in result.rows)

    def test_fetch_unknown_keyword_returns_fallback(self):
        c = DryRunTrendsConnector()
        result = c.fetch(keywords=["absolutely-unknown-xyz"], **_DATE_RANGE)
        assert len(result.rows) >= 1  # falls back to first 3

    def test_no_real_import_needed(self):
        # If pytrends is not installed this must still work
        c = DryRunTrendsConnector()
        result = c.fetch(keywords=[], **_DATE_RANGE)
        assert isinstance(result, IntelligenceFetchResult)


# ---------------------------------------------------------------------------
# Competitor Monitor
# ---------------------------------------------------------------------------


class TestDryRunCompetitorMonitor:
    def test_source(self):
        assert DryRunCompetitorMonitor().source == "competitor_monitor"

    def test_fixture_rows_structure(self):
        c = DryRunCompetitorMonitor()
        result = c.fetch(keywords=[], **_DATE_RANGE)
        assert len(result.rows) >= 1
        row = result.rows[0]
        assert "competitor_name" in row
        assert "observation_type" in row
        assert "summary" in row

    def test_not_ready(self):
        assert DryRunCompetitorMonitor().availability().is_ready is False


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------


class TestDryRunRedditConnector:
    def test_source(self):
        assert DryRunRedditConnector().source == "reddit"

    def test_fixture_rows_structure(self):
        c = DryRunRedditConnector()
        result = c.fetch(keywords=[], **_DATE_RANGE)
        assert len(result.rows) >= 1
        row = result.rows[0]
        assert "title" in row
        assert "upvotes" in row

    def test_filter_by_keyword(self):
        c = DryRunRedditConnector()
        result = c.fetch(keywords=["LinkedIn"], **_DATE_RANGE)
        assert len(result.rows) >= 1

    def test_not_ready(self):
        assert DryRunRedditConnector().availability().is_ready is False


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


class TestDryRunYouTubeConnector:
    def test_source(self):
        assert DryRunYouTubeConnector().source == "youtube"

    def test_fixture_rows_structure(self):
        c = DryRunYouTubeConnector()
        result = c.fetch(keywords=[], **_DATE_RANGE)
        assert len(result.rows) >= 1
        row = result.rows[0]
        assert "video_id" in row
        assert "view_count" in row

    def test_not_ready(self):
        assert DryRunYouTubeConnector().availability().is_ready is False


# ---------------------------------------------------------------------------
# Meta Ads
# ---------------------------------------------------------------------------


class TestDryRunMetaAdsConnector:
    def test_source(self):
        assert DryRunMetaAdsConnector().source == "meta_ads_library"

    def test_fixture_rows_structure(self):
        c = DryRunMetaAdsConnector()
        result = c.fetch(keywords=[], **_DATE_RANGE)
        assert len(result.rows) >= 1
        row = result.rows[0]
        assert "advertiser" in row
        assert "ad_text" in row
        assert "platforms" in row

    def test_filter_by_keyword(self):
        c = DryRunMetaAdsConnector()
        result = c.fetch(keywords=["agency"], **_DATE_RANGE)
        assert any("agency" in r.get("keywords_matched", []) for r in result.rows)

    def test_not_ready(self):
        assert DryRunMetaAdsConnector().availability().is_ready is False


# ---------------------------------------------------------------------------
# Safety: no mutation methods on any connector
# ---------------------------------------------------------------------------


def test_no_write_methods_on_connectors():
    """Ensure no connector exposes write/create/delete/update methods."""
    forbidden = {"write", "create", "delete", "update", "post", "patch", "put"}
    for cls in [
        DryRunIntelligenceConnector,
        DryRunTrendsConnector,
        DryRunCompetitorMonitor,
        DryRunRedditConnector,
        DryRunYouTubeConnector,
        DryRunMetaAdsConnector,
    ]:
        public_methods = {
            name
            for name in dir(cls)
            if not name.startswith("_") and callable(getattr(cls, name))
        }
        overlap = public_methods & forbidden
        assert not overlap, (
            f"{cls.__name__} exposes forbidden mutation method(s): {overlap}"
        )
