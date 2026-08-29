"""MKT-10X — Google Trends connector (dry-run fixture implementation).

Real implementation would use ``pytrends`` (optional extra, not yet
installed). This module ships a ``DryRunTrendsConnector`` that returns
deterministic fixture data without any network calls or SDK imports.

Future: add ``PyTrendsTrendsConnector`` behind
``pip install -e .[intelligence]`` once the extra is defined.
"""

from __future__ import annotations

from datetime import date

from .base import (
    DryRunIntelligenceConnector,
    IntelligenceFetchResult,
)

_SOURCE = "google_trends"

_FIXTURE_ROWS: list[dict[str, object]] = [
    {
        "keyword": "marketing automation",
        "relative_interest": 72.0,
        "direction": "rising",
        "region": "global",
    },
    {
        "keyword": "content marketing strategy",
        "relative_interest": 55.0,
        "direction": "stable",
        "region": "global",
    },
    {
        "keyword": "social media ads",
        "relative_interest": 88.0,
        "direction": "rising",
        "region": "global",
    },
    {
        "keyword": "email marketing roi",
        "relative_interest": 41.0,
        "direction": "falling",
        "region": "global",
    },
    {
        "keyword": "short form video",
        "relative_interest": 95.0,
        "direction": "rising",
        "region": "global",
    },
]


class DryRunTrendsConnector(DryRunIntelligenceConnector):
    """Returns fixture trend data. No pytrends import, no network call."""

    def __init__(self) -> None:
        super().__init__(_SOURCE, reason="dry-run: pytrends not wired")

    def fetch(
        self,
        *,
        keywords: list[str],
        start_date: date,
        end_date: date,
    ) -> IntelligenceFetchResult:
        del start_date, end_date
        if keywords:
            rows = [r for r in _FIXTURE_ROWS if r["keyword"] in keywords]
            if not rows:
                rows = _FIXTURE_ROWS[:3]
        else:
            rows = list(_FIXTURE_ROWS)
        return IntelligenceFetchResult(
            rows=rows,
            source=_SOURCE,
            notes=["dry-run fixture data — no real pytrends call made"],
        )


__all__ = ["DryRunTrendsConnector"]
