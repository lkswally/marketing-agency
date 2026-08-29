"""MKT-10X — Competitor website monitor (dry-run fixture implementation).

Real implementation would use ``requests`` + ``beautifulsoup4`` to scrape
public pages. This module ships only the dry-run variant: no HTTP, no SDK.

Future: add ``RequestsCompetitorMonitor`` behind opt-in credentials.
"""

from __future__ import annotations

from datetime import date

from .base import (
    DryRunIntelligenceConnector,
    IntelligenceFetchResult,
)

_SOURCE = "competitor_monitor"

_FIXTURE_ROWS: list[dict[str, object]] = [
    {
        "competitor_name": "CompetitorA",
        "competitor_url": "https://example-competitor-a.com",
        "observation_type": "new_content",
        "summary": "Published 3 new blog posts about AI-powered marketing this week.",
        "source_url": "https://example-competitor-a.com/blog",
        "confidence": "medium",
    },
    {
        "competitor_name": "CompetitorB",
        "competitor_url": "https://example-competitor-b.com",
        "observation_type": "new_offer",
        "summary": "Launched a free tier targeting SMB segment.",
        "source_url": "https://example-competitor-b.com/pricing",
        "confidence": "high",
    },
    {
        "competitor_name": "CompetitorC",
        "competitor_url": "https://example-competitor-c.com",
        "observation_type": "social_activity",
        "summary": "Increased LinkedIn posting frequency from 2x to 5x per week.",
        "source_url": None,
        "confidence": "low",
    },
]


class DryRunCompetitorMonitor(DryRunIntelligenceConnector):
    """Returns fixture competitor observations. No HTTP calls."""

    def __init__(self) -> None:
        super().__init__(_SOURCE, reason="dry-run: requests/bs4 not wired")

    def fetch(
        self,
        *,
        keywords: list[str],
        start_date: date,
        end_date: date,
    ) -> IntelligenceFetchResult:
        del keywords, start_date, end_date
        return IntelligenceFetchResult(
            rows=list(_FIXTURE_ROWS),
            source=_SOURCE,
            notes=["dry-run fixture data — no real HTTP call made"],
        )


__all__ = ["DryRunCompetitorMonitor"]
