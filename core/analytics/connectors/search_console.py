"""Search Console read-only adapter (MKT-6D).

Wraps the Search Console v1 API (Webmasters) via
``googleapiclient.discovery.build("searchconsole", "v1", ...)``
and restricts usage to ``searchanalytics().query()`` (read). The
SDK is lazy-imported inside :meth:`availability` and :meth:`fetch`
so the module loads without the dependency installed.

Environment variables (read at availability check, never logged):

- ``GOOGLE_APPLICATION_CREDENTIALS`` — path to a service-account
  JSON. The path is checked for existence; the contents are never
  read by this module.
- ``SEARCH_CONSOLE_SITE_URL`` — the verified site (``https://...``
  or ``sc-domain:...``) to query. Persisted only as a
  hash-truncated fingerprint.

**Read-only strict.** This module deliberately does not import or
reference any mutating Search Console resource (``sitemaps``,
``sites`` add/delete, etc.). The safety test suite grep-asserts
that no mutation method name appears in this file's source.
"""

from __future__ import annotations

import os
from datetime import date

from .base import (
    AVAILABILITY_OK,
    AnalyticsConnector,
    ConnectorAvailability,
    FetchResult,
)

_ENV_CREDENTIALS = "GOOGLE_APPLICATION_CREDENTIALS"
_ENV_SITE_URL = "SEARCH_CONSOLE_SITE_URL"

_QUERY_DIMENSIONS: tuple[str, ...] = ("date", "query", "page")
_QUERY_ROW_LIMIT = 1000


class SearchConsoleReadOnlyConnector(AnalyticsConnector):
    """Reads Search Console search analytics via the v1 API."""

    def __init__(self, *, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    @property
    def source(self) -> str:
        return "search_console"

    # ---------- availability ----------

    def availability(self) -> ConnectorAvailability:
        creds_path = self._env.get(_ENV_CREDENTIALS, "").strip()
        site_url = self._env.get(_ENV_SITE_URL, "").strip()

        credentials_available = bool(creds_path) and bool(site_url)
        creds_reason = ""
        if not creds_path:
            creds_reason = f"missing env {_ENV_CREDENTIALS}"
        elif not site_url:
            creds_reason = f"missing env {_ENV_SITE_URL}"
        elif not os.path.exists(creds_path):
            credentials_available = False
            creds_reason = (
                f"{_ENV_CREDENTIALS} points to a path that does not exist"
            )

        sdk_available = _sc_sdk_importable()
        sdk_reason = "" if sdk_available else "google-api-python-client not installed"

        if sdk_available and credentials_available:
            return ConnectorAvailability(
                sdk_available=True,
                credentials_available=True,
                reason=AVAILABILITY_OK,
            )
        reason = "; ".join(r for r in (sdk_reason, creds_reason) if r)
        return ConnectorAvailability(
            sdk_available=sdk_available,
            credentials_available=credentials_available,
            reason=reason or "connector unavailable",
        )

    # ---------- fetch ----------

    def fetch(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> FetchResult:
        site_url = self._env.get(_ENV_SITE_URL, "").strip()
        if not site_url:
            return FetchResult(rows=[], identifier=None, notes=[
                f"missing env {_ENV_SITE_URL}; no fetch performed",
            ])

        service = self._build_service()
        body = self._build_request_body(start_date=start_date, end_date=end_date)
        # The service object exposes ``searchanalytics().query(...)``
        # only — this module imports nothing that could write.
        response = (
            service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        )

        rows: list[dict[str, object]] = []
        for raw_row in response.get("rows", []) or []:
            keys = raw_row.get("keys", []) or []
            row: dict[str, object] = {}
            for i, dim in enumerate(_QUERY_DIMENSIONS):
                row[dim] = keys[i] if i < len(keys) else ""
            row["clicks"] = raw_row.get("clicks", 0.0)
            row["impressions"] = raw_row.get("impressions", 0.0)
            row["ctr"] = raw_row.get("ctr", 0.0)
            row["position"] = raw_row.get("position", 0.0)
            rows.append(row)
        return FetchResult(rows=rows, identifier=site_url)

    # ---------- internals (lazy import boundary) ----------

    def _build_service(self):  # type: ignore[no-untyped-def]
        # Lazy import — keeps the module dependency-free until a
        # real fetch runs. Tests patch ``_build_service`` directly.
        from googleapiclient.discovery import build  # type: ignore[import-not-found]

        return build("searchconsole", "v1", cache_discovery=False)

    def _build_request_body(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, object]:
        return {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": list(_QUERY_DIMENSIONS),
            "rowLimit": _QUERY_ROW_LIMIT,
        }


def _sc_sdk_importable() -> bool:
    try:
        import importlib

        importlib.import_module("googleapiclient.discovery")
    except Exception:  # noqa: BLE001
        return False
    return True


__all__ = ["SearchConsoleReadOnlyConnector"]
