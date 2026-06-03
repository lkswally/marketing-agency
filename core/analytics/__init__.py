"""Manual marketing analytics import + analysis (MKT-6A).

Two contracts ship in this block:

- ``metrics-snapshot.v1`` — normalised per-row data from one or
  more manual imports (CSV / JSON).
- ``optimization-recommendation-pack.v1`` — analysis output with
  per-channel rankings, SEO opportunities, content top performers
  and explicit "repeat this / pause that / improve this / next
  action" recommendations.

**No external API. No MCP. No GA4 / Search Console / Ads / Social
client. No credential read.** Operators export data manually from
the source platform and feed the files to ``mkt import-metrics``.
"""

from __future__ import annotations

from .analyzer import AnalyticsAnalyzer, analyze_and_persist
from .importer import (
    AnalyticsImporter,
    ImporterError,
    import_and_persist,
)
from .models import (
    ANALYTICS_IMPORT_REPORT_KIND,
    ANALYTICS_IMPORT_REPORT_VERSION,
    METRICS_SNAPSHOT_KIND,
    METRICS_SNAPSHOT_VERSION,
    OPTIMIZATION_RECOMMENDATION_PACK_KIND,
    OPTIMIZATION_RECOMMENDATION_PACK_VERSION,
    SINGLETON_ID,
    AnalyticsImportReport,
    ChannelPerformanceSummary,
    ContentPerformanceSummary,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
    OptimizationRecommendation,
    OptimizationRecommendationPack,
    Recommendation,
    SEOOpportunity,
    SEOOpportunityReport,
)
from .renderer import (
    render_markdown_import_report,
    render_markdown_recommendations,
)

__all__ = [
    "ANALYTICS_IMPORT_REPORT_KIND",
    "ANALYTICS_IMPORT_REPORT_VERSION",
    "AnalyticsAnalyzer",
    "AnalyticsImportReport",
    "AnalyticsImporter",
    "ChannelPerformanceSummary",
    "ContentPerformanceSummary",
    "ImporterError",
    "METRICS_SNAPSHOT_KIND",
    "METRICS_SNAPSHOT_VERSION",
    "MetricRow",
    "MetricSource",
    "MetricsSnapshot",
    "OPTIMIZATION_RECOMMENDATION_PACK_KIND",
    "OPTIMIZATION_RECOMMENDATION_PACK_VERSION",
    "OptimizationRecommendation",
    "OptimizationRecommendationPack",
    "Recommendation",
    "SEOOpportunity",
    "SEOOpportunityReport",
    "SINGLETON_ID",
    "analyze_and_persist",
    "import_and_persist",
    "render_markdown_import_report",
    "render_markdown_recommendations",
]
