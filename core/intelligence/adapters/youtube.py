"""MKT-10X — YouTube Data API connector (dry-run fixture implementation).

Real implementation would use ``google-api-python-client`` with an API key.
This module ships only the dry-run variant: no HTTP, no SDK import.

Future: add ``YouTubeDataConnector`` behind ``pip install -e .[intelligence]``.
"""

from __future__ import annotations

from datetime import date

from .base import (
    DryRunIntelligenceConnector,
    IntelligenceFetchResult,
)

_SOURCE = "youtube"

_FIXTURE_ROWS: list[dict[str, object]] = [
    {
        "video_id": "fixture-yt-001",
        "title": "How to Build a B2B Content Strategy in 2024",
        "channel": "MarketingExpert",
        "view_count": 45200,
        "like_count": 1340,
        "comment_count": 89,
        "published_at": "2024-01-15",
        "keywords_matched": ["B2B", "content strategy"],
    },
    {
        "video_id": "fixture-yt-002",
        "title": "LinkedIn Ads Tutorial: From Zero to 10x ROAS",
        "channel": "PaidMediaPro",
        "view_count": 128000,
        "like_count": 4100,
        "comment_count": 312,
        "published_at": "2024-02-03",
        "keywords_matched": ["LinkedIn Ads", "ROAS"],
    },
    {
        "video_id": "fixture-yt-003",
        "title": "Short-Form Video Strategy for Brands — Full Playbook",
        "channel": "SocialMediaAcademy",
        "view_count": 87300,
        "like_count": 2900,
        "comment_count": 204,
        "published_at": "2024-03-11",
        "keywords_matched": ["short-form video", "brands"],
    },
]


class DryRunYouTubeConnector(DryRunIntelligenceConnector):
    """Returns fixture YouTube video data. No network calls."""

    def __init__(self) -> None:
        super().__init__(_SOURCE, reason="dry-run: YouTube Data API not wired")

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
            notes=["dry-run fixture data — no real YouTube API call made"],
        )


__all__ = ["DryRunYouTubeConnector"]
