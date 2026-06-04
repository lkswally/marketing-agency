"""Google Analytics + Search Console read-only connectors (MKT-6D).

Two adapters ship in this block:

- :class:`GA4ReadOnlyConnector` — reads from Google Analytics 4
  (Data API v1beta) using ``run_report`` only. No mutation.
- :class:`SearchConsoleReadOnlyConnector` — reads from Search
  Console (Webmasters v1) using ``searchanalytics().query()``
  only. No mutation.

Both connectors lazy-import the official Google SDK. If the SDK
is not installed or credentials are missing, the connector is
considered *unavailable* and the fetch degrades to a controlled
no-op with ``status="skipped"``. The system never crashes on
missing credentials.

**Read-only strict.** No write call. No Google Ads. No MCP. No
n8n. No HTTP manual. No scraping. No credentials in repo. No
logging of credentials. Sensitive IDs are hash-truncated in
reports.

The manual CSV importer (MKT-6A) keeps working unchanged and
remains the supported fallback when no real connector is wired.
"""

from __future__ import annotations

from .base import (
    AVAILABILITY_OK,
    AnalyticsConnector,
    ConnectorAvailability,
    DryRunConnector,
)
from .ga4 import GA4ReadOnlyConnector
from .models import (
    ANALYTICS_FETCH_REPORT_KIND,
    ANALYTICS_FETCH_REPORT_VERSION,
    SUPPORTED_SOURCES,
    AnalyticsFetchReport,
    FetchStatus,
)
from .normalizer import (
    normalize_ga4_rows,
    normalize_search_console_rows,
)
from .search_console import SearchConsoleReadOnlyConnector
from .service import (
    DEFAULT_LOOKBACK_DAYS,
    AnalyticsFetchService,
    fetch_and_persist,
    resolve_connector,
)

__all__ = [
    "ANALYTICS_FETCH_REPORT_KIND",
    "ANALYTICS_FETCH_REPORT_VERSION",
    "AVAILABILITY_OK",
    "AnalyticsConnector",
    "AnalyticsFetchReport",
    "AnalyticsFetchService",
    "ConnectorAvailability",
    "DEFAULT_LOOKBACK_DAYS",
    "DryRunConnector",
    "FetchStatus",
    "GA4ReadOnlyConnector",
    "SUPPORTED_SOURCES",
    "SearchConsoleReadOnlyConnector",
    "fetch_and_persist",
    "normalize_ga4_rows",
    "normalize_search_console_rows",
    "resolve_connector",
]
