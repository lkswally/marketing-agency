"""Row normalisation for the GA4 / Search Console connectors (MKT-6D).

Each connector returns connector-native row dicts (GA4 dimension
names, Search Console keys). This module turns those into
:class:`core.analytics.MetricRow` instances so the rest of the
analytics pipeline (analyzer, feedback planner, iteration planner)
can treat connector data uniformly with the manual CSV importer's
output.

GA4 metric → ``MetricRow.metric_name`` mapping
-----------------------------------------------

The GA4 Data API returns metrics with camelCase names. We
lowercase-snake-case them and normalise a few well-known ones to
match the conventions the analyzer recognises:

- ``totalUsers`` → ``users``
- ``bounceRate`` → ``bounce_rate`` (already 0..1 fraction in v1beta)
- ``sessions``, ``conversions`` → unchanged

GA4 default channel grouping → ``MetricRow.channel`` mapping
------------------------------------------------------------

GA4 returns ``Organic Search``, ``Direct``, ``Referral`` etc.
We slugify these (``organic_search`` etc.) so downstream
aggregations match the slugs used by the manual importer.

Search Console row → ``MetricRow``
----------------------------------

Search Console rows always produce 4 metric rows
(``clicks``, ``impressions``, ``ctr``, ``position``) tagged with
``MetricSource.SEARCH_CONSOLE`` and channel ``organic_search`` —
identical to the manual importer's behaviour so the downstream
analysis is identical.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime

from core.analytics.models import MetricRow, MetricSource

_GA4_METRIC_RENAME: dict[str, str] = {
    "totalusers": "users",
    "totalUsers": "users",
    "bouncerate": "bounce_rate",
    "bounceRate": "bounce_rate",
    "sessions": "sessions",
    "conversions": "conversions",
}

_GA4_DIM_DATE = "date"
_GA4_DIM_CHANNEL = "sessionDefaultChannelGroup"
_GA4_DIM_PAGE = "pagePath"


def normalize_ga4_rows(rows: list[dict[str, object]]) -> tuple[list[MetricRow], list[str]]:
    """Convert GA4 raw rows to :class:`MetricRow` plus rejection reasons."""

    out: list[MetricRow] = []
    reasons: list[str] = []
    for i, raw in enumerate(rows):
        parsed_date = _parse_ga4_date(_str(raw.get(_GA4_DIM_DATE)))
        channel = _slugify_ga4_channel(_str(raw.get(_GA4_DIM_CHANNEL)))
        page = _str(raw.get(_GA4_DIM_PAGE)) or None
        any_metric = False
        for key, value in raw.items():
            if key in (_GA4_DIM_DATE, _GA4_DIM_CHANNEL, _GA4_DIM_PAGE):
                continue
            metric_name = _GA4_METRIC_RENAME.get(key) or _GA4_METRIC_RENAME.get(
                key.lower()
            ) or _to_snake(key)
            number = _to_float(value)
            if number is None:
                continue
            out.append(
                MetricRow(
                    source=MetricSource.GA4,
                    event_date=parsed_date,
                    channel=channel or "organic_search",
                    content_ref=page,
                    metric_name=metric_name,
                    value=number,
                )
            )
            any_metric = True
        if not any_metric:
            reasons.append(f"row {i + 1}: no GA4 numeric metric found")
    return out, reasons


def normalize_search_console_rows(
    rows: list[dict[str, object]],
) -> tuple[list[MetricRow], list[str]]:
    """Convert Search Console raw rows to :class:`MetricRow`."""

    out: list[MetricRow] = []
    reasons: list[str] = []
    for i, raw in enumerate(rows):
        parsed_date = _parse_ga4_date(_str(raw.get("date")))
        page = _str(raw.get("page")) or None
        query = _str(raw.get("query")) or None
        any_metric = False
        for metric_name in ("clicks", "impressions", "ctr", "position"):
            if metric_name not in raw:
                continue
            number = _to_float(raw[metric_name])
            if number is None:
                continue
            out.append(
                MetricRow(
                    source=MetricSource.SEARCH_CONSOLE,
                    event_date=parsed_date,
                    channel="organic_search",
                    content_ref=page,
                    query=query,
                    metric_name=metric_name,
                    value=number,
                )
            )
            any_metric = True
        if not any_metric:
            reasons.append(f"row {i + 1}: no Search Console numeric metric found")
    return out, reasons


# ---------- helpers ----------


def _str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_ga4_date(s: str) -> _date | None:
    if not s:
        return None
    # GA4 returns ``YYYYMMDD`` for the ``date`` dimension. Search
    # Console returns ``YYYY-MM-DD``. We accept both.
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _slugify_ga4_channel(s: str) -> str:
    s = (s or "").strip().lower()
    if not s:
        return ""
    out_chars: list[str] = []
    last_dash = False
    for ch in s:
        if ch.isalnum():
            out_chars.append(ch)
            last_dash = False
        elif not last_dash:
            out_chars.append("_")
            last_dash = True
    return "".join(out_chars).strip("_")


def _to_snake(s: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        # Booleans are technically ints in Python; reject explicitly
        # since GA4 metrics are never boolean.
        return None
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    is_percent = s.endswith("%")
    if is_percent:
        s = s[:-1].strip()
    s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if is_percent:
        v /= 100.0
    return v


__all__ = [
    "normalize_ga4_rows",
    "normalize_search_console_rows",
]
