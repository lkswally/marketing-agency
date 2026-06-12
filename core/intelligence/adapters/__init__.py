"""MKT-10X — dry-run intelligence adapters.

Each adapter follows the same pattern as :mod:`core.analytics.connectors`:
- ``availability()`` → ``IntelligenceAvailability``
- ``fetch()`` → ``IntelligenceFetchResult``

In this block ALL adapters are dry-run only. Real HTTP calls are gated
behind optional extras that are NOT installed here.
"""

from .base import (
    DryRunIntelligenceConnector,
    IntelligenceAvailability,
    IntelligenceConnector,
    IntelligenceFetchResult,
)
from .competitor_monitor import DryRunCompetitorMonitor
from .meta_ads import DryRunMetaAdsConnector
from .reddit import DryRunRedditConnector
from .trends import DryRunTrendsConnector
from .youtube import DryRunYouTubeConnector

__all__ = [
    "DryRunCompetitorMonitor",
    "DryRunIntelligenceConnector",
    "DryRunMetaAdsConnector",
    "DryRunRedditConnector",
    "DryRunTrendsConnector",
    "DryRunYouTubeConnector",
    "IntelligenceAvailability",
    "IntelligenceConnector",
    "IntelligenceFetchResult",
]
