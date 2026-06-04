"""Google Ads native analyzer rules (MKT-6F).

Adds a Google-Ads-specific analyzer on top of the
:class:`MetricsSnapshot` model. Reads rows tagged with
``MetricSource.GOOGLE_ADS`` (produced by the MKT-6E connector or
manual CSV imports), aggregates them per ``content_ref``
(campaign + ad_group) and surfaces structured insights with
explicit suggested actions.

Contract: ``google-ads-insight-pack.v1``.

**No external API. No Google Ads write. No campaign mutation.**
The pack contains suggestions only; an operator reviews and
decides whether to apply them in the Ads UI manually.
"""

from __future__ import annotations

from .analyzer import (
    DEFAULT_ADS_ANALYZER_RULE_SET_ID,
    GoogleAdsAnalyzer,
    analyze_and_persist_ads,
)
from .models import (
    GOOGLE_ADS_INSIGHT_PACK_KIND,
    GOOGLE_ADS_INSIGHT_PACK_VERSION,
    SINGLETON_ID,
    AdGroupProfile,
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)
from .renderer import render_markdown_ads_insights

__all__ = [
    "AdGroupProfile",
    "AdsInsightAction",
    "AdsInsightKind",
    "AdsInsightSeverity",
    "AdsInsightStats",
    "DEFAULT_ADS_ANALYZER_RULE_SET_ID",
    "GOOGLE_ADS_INSIGHT_PACK_KIND",
    "GOOGLE_ADS_INSIGHT_PACK_VERSION",
    "GoogleAdsAnalyzer",
    "GoogleAdsInsight",
    "GoogleAdsInsightPack",
    "SINGLETON_ID",
    "analyze_and_persist_ads",
    "render_markdown_ads_insights",
]
