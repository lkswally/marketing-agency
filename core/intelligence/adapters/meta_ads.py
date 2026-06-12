"""MKT-10X — Meta Ads Library connector (dry-run fixture implementation).

Real implementation would use the Meta Ads Library public API (read-only,
requires app token). This module ships only the dry-run variant.

Future: add ``MetaAdsLibraryConnector`` behind opt-in credentials.
"""

from __future__ import annotations

from datetime import date

from .base import (
    DryRunIntelligenceConnector,
    IntelligenceFetchResult,
)

_SOURCE = "meta_ads_library"

_FIXTURE_ROWS: list[dict[str, object]] = [
    {
        "ad_id": "fixture-meta-001",
        "advertiser": "CompetitorA",
        "ad_text": "Struggling with your marketing? Our platform helps you 3× leads in 90 days.",
        "cta": "Learn More",
        "platforms": ["facebook", "instagram"],
        "start_date": "2024-01-10",
        "active": True,
        "keywords_matched": ["marketing", "leads"],
    },
    {
        "ad_id": "fixture-meta-002",
        "advertiser": "CompetitorB",
        "ad_text": "Free forever plan — no credit card. Start automating today.",
        "cta": "Sign Up Free",
        "platforms": ["facebook"],
        "start_date": "2024-02-20",
        "active": True,
        "keywords_matched": ["free", "automation"],
    },
    {
        "ad_id": "fixture-meta-003",
        "advertiser": "CompetitorC",
        "ad_text": "Join 10,000+ agencies using our AI-powered creative suite.",
        "cta": "Get Demo",
        "platforms": ["instagram"],
        "start_date": "2024-03-05",
        "active": False,
        "keywords_matched": ["agency", "AI", "creative"],
    },
]


class DryRunMetaAdsConnector(DryRunIntelligenceConnector):
    """Returns fixture Meta Ads Library data. No network calls."""

    def __init__(self) -> None:
        super().__init__(_SOURCE, reason="dry-run: Meta Ads Library API not wired")

    def fetch(
        self,
        *,
        keywords: list[str],
        start_date: date,
        end_date: date,
    ) -> IntelligenceFetchResult:
        del start_date, end_date
        if keywords:
            rows = [
                r
                for r in _FIXTURE_ROWS
                if any(kw in r.get("keywords_matched", []) for kw in keywords)
            ]
            if not rows:
                rows = _FIXTURE_ROWS[:2]
        else:
            rows = list(_FIXTURE_ROWS)
        return IntelligenceFetchResult(
            rows=rows,
            source=_SOURCE,
            notes=["dry-run fixture data — no real Meta Ads Library API call made"],
        )


__all__ = ["DryRunMetaAdsConnector"]
