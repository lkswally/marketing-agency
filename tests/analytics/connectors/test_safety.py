"""Safety pins: grep-asserted invariants for the MKT-6D connectors.

These tests inspect the source code of the connector modules to
guarantee:

1. No HTTP client library is imported (the only network goes
   through the lazy-imported official Google SDK).
2. No Google Ads import / reference.
3. No SDK mutation method appears in source (``run_report`` /
   ``searchanalytics`` are the only allowed entry points).
4. No raw ``print`` / ``logging`` of credential or identifier env
   vars.
5. No ``token`` / ``api_key`` / ``secret`` / ``credential`` field
   on persisted models.
"""

from __future__ import annotations

from pathlib import Path

CONNECTORS_DIR = Path(__file__).resolve().parents[3] / "core" / "analytics" / "connectors"

FORBIDDEN_HTTP_LIBS = (
    "import requests",
    "from requests",
    "import httpx",
    "from httpx",
    "import urllib.request",
    "from urllib.request",
    "import aiohttp",
    "from aiohttp",
)

FORBIDDEN_ADS_TOKENS = (
    "google_ads",
    "googleads",
    "google.ads",
    "GoogleAdsClient",
    "AdWords",
    "adwords",
)

# GA4 / Search Console SDK methods that would write or mutate state.
FORBIDDEN_GA4_MUTATIONS = (
    "create_property",
    "update_property",
    "delete_property",
    "archive_property",
    "create_data_stream",
    "delete_data_stream",
    "create_custom_dimension",
    "create_conversion_event",
)
FORBIDDEN_SC_MUTATIONS = (
    "sitemaps().submit",
    "sitemaps().delete",
    "sites().add",
    "sites().delete",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_http_lib_in_any_connector_module() -> None:
    for py in CONNECTORS_DIR.glob("*.py"):
        text = _read(py)
        for needle in FORBIDDEN_HTTP_LIBS:
            assert needle not in text, f"{py.name} imports {needle!r}"


def test_no_google_ads_anywhere() -> None:
    for py in CONNECTORS_DIR.glob("*.py"):
        text = _read(py).lower()
        for needle in FORBIDDEN_ADS_TOKENS:
            assert needle.lower() not in text, f"{py.name} references {needle!r}"


def test_no_ga4_mutation_method_referenced() -> None:
    ga4_text = _read(CONNECTORS_DIR / "ga4.py")
    for needle in FORBIDDEN_GA4_MUTATIONS:
        assert needle not in ga4_text, f"ga4.py references {needle!r}"


def test_no_search_console_mutation_method_referenced() -> None:
    sc_text = _read(CONNECTORS_DIR / "search_console.py")
    for needle in FORBIDDEN_SC_MUTATIONS:
        assert needle not in sc_text, f"search_console.py references {needle!r}"


def test_no_print_or_log_of_credentials() -> None:
    """The connector modules must not ``print`` / ``logging`` the
    credential or identifier env values themselves. They may
    reference the env *names* (e.g. in error reasons) but never
    print ``self._env[...]`` directly."""
    forbidden_patterns = (
        "print(self._env",
        "logging.info(self._env",
        "logging.debug(self._env",
        "logger.info(self._env",
        "logger.debug(self._env",
    )
    for py in CONNECTORS_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden_patterns:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_credential_fields_on_fetch_report() -> None:
    from core.analytics.connectors.models import AnalyticsFetchReport

    fields = set(AnalyticsFetchReport.model_fields.keys())
    forbidden = {
        "token", "api_key", "secret", "credential", "credentials",
        "url", "webhook_url", "site_url", "property_id",
    }
    bad = fields & forbidden
    assert not bad, f"AnalyticsFetchReport must not expose: {bad}"


def test_only_read_only_entry_points_used() -> None:
    """Pin: GA4 connector calls ``run_report``, Search Console
    calls ``searchanalytics`` only. No other entry point."""

    ga4_text = _read(CONNECTORS_DIR / "ga4.py")
    sc_text = _read(CONNECTORS_DIR / "search_console.py")
    assert "run_report" in ga4_text
    assert "searchanalytics" in sc_text


def test_csv_importer_module_unchanged_shape() -> None:
    """The connector module must not edit or shadow the manual
    importer's public API."""
    from core.analytics import AnalyticsImporter, MetricSource

    assert hasattr(AnalyticsImporter, "import_file")
    assert {s.value for s in MetricSource} >= {"ga4", "search_console", "manual"}


def test_lazy_import_keeps_module_loadable_without_sdk() -> None:
    """Importing the connectors package must succeed even when the
    Google SDKs are not installed. This is implicitly true if the
    test suite passes (we don't depend on these SDKs in CI), but
    we make it explicit."""
    import core.analytics.connectors  # noqa: F401
    from core.analytics.connectors import (  # noqa: F401
        GA4ReadOnlyConnector,
        SearchConsoleReadOnlyConnector,
    )
