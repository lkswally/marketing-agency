"""MKT-10X — Reddit public read connector (dry-run fixture implementation).

Real implementation would use the Reddit public JSON API (no auth for
read-only, rate-limit aware). This module ships only the dry-run variant.

Future: add ``RedditPublicConnector`` using ``requests`` + public endpoints.
"""

from __future__ import annotations

from datetime import date

from .base import (
    DryRunIntelligenceConnector,
    IntelligenceFetchResult,
)

_SOURCE = "reddit"

_FIXTURE_ROWS: list[dict[str, object]] = [
    {
        "subreddit": "r/marketing",
        "title": "What's your current best-performing content format in 2024?",
        "upvotes": 342,
        "comment_count": 87,
        "url": "https://reddit.com/r/marketing/fixture-1",
        "sentiment": "neutral",
        "keywords_matched": ["content format", "marketing"],
    },
    {
        "subreddit": "r/entrepreneur",
        "title": "Short-form video is eating long-form alive — data from my agency",
        "upvotes": 1204,
        "comment_count": 213,
        "url": "https://reddit.com/r/entrepreneur/fixture-2",
        "sentiment": "positive",
        "keywords_matched": ["short-form video", "agency"],
    },
    {
        "subreddit": "r/socialmedia",
        "title": "LinkedIn organic reach dropped 40% — what are you doing about it?",
        "upvotes": 567,
        "comment_count": 134,
        "url": "https://reddit.com/r/socialmedia/fixture-3",
        "sentiment": "negative",
        "keywords_matched": ["LinkedIn", "organic reach"],
    },
]


class DryRunRedditConnector(DryRunIntelligenceConnector):
    """Returns fixture Reddit posts. No network calls."""

    def __init__(self) -> None:
        super().__init__(_SOURCE, reason="dry-run: Reddit API not wired")

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
            notes=["dry-run fixture data — no real Reddit API call made"],
        )


__all__ = ["DryRunRedditConnector"]
