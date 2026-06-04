"""GA4 read-only adapter (MKT-6D).

Wraps ``google.analytics.data_v1beta.BetaAnalyticsDataClient`` and
restricts usage to ``run_report`` (read). The SDK is lazy-imported
inside :meth:`availability` and :meth:`fetch` so the module loads
without the dependency installed and tests never pull it in.

Environment variables (read at availability check, never logged):

- ``GOOGLE_APPLICATION_CREDENTIALS`` — path to a service-account
  JSON. The path is checked for existence; the contents are never
  read by this module.
- ``GA4_PROPERTY_ID`` — numeric property id of the GA4 property to
  read. Persisted only as a hash-truncated fingerprint.

**Read-only strict.** This module deliberately does not import or
reference any GA4 client method beyond ``run_report``. The safety
test suite grep-asserts that no mutation method name appears in
this file's source.
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
_ENV_PROPERTY_ID = "GA4_PROPERTY_ID"

_REPORT_METRICS: tuple[str, ...] = (
    "sessions",
    "totalUsers",
    "conversions",
    "bounceRate",
)
_REPORT_DIMENSIONS: tuple[str, ...] = ("date", "sessionDefaultChannelGroup", "pagePath")


class GA4ReadOnlyConnector(AnalyticsConnector):
    """Reads GA4 reports via the official Data API v1beta SDK."""

    def __init__(self, *, env: dict[str, str] | None = None) -> None:
        # ``env`` lets tests inject an isolated dict instead of the
        # real ``os.environ``. In production it is always ``None``
        # and the connector reads the live environment.
        self._env = env if env is not None else os.environ

    @property
    def source(self) -> str:
        return "ga4"

    # ---------- availability ----------

    def availability(self) -> ConnectorAvailability:
        creds_path = self._env.get(_ENV_CREDENTIALS, "").strip()
        property_id = self._env.get(_ENV_PROPERTY_ID, "").strip()

        credentials_available = bool(creds_path) and bool(property_id)
        creds_reason = ""
        if not creds_path:
            creds_reason = f"missing env {_ENV_CREDENTIALS}"
        elif not property_id:
            creds_reason = f"missing env {_ENV_PROPERTY_ID}"
        elif not os.path.exists(creds_path):
            credentials_available = False
            creds_reason = (
                f"{_ENV_CREDENTIALS} points to a path that does not exist"
            )

        sdk_available = _ga4_sdk_importable()
        sdk_reason = (
            "" if sdk_available else "google-analytics-data SDK not installed"
        )

        if sdk_available and credentials_available:
            return ConnectorAvailability(
                sdk_available=True,
                credentials_available=True,
                reason=AVAILABILITY_OK,
            )

        # Compose a single human reason; SDK first since it is the
        # harder-to-fix gap.
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
        """Run a single read-only report and return the raw row dicts.

        Exceptions from the SDK (network, permission, quota) are
        intentionally not caught here — the service layer wraps the
        call in try/except and produces a ``FAILED`` report.
        """

        property_id = self._env.get(_ENV_PROPERTY_ID, "").strip()
        if not property_id:
            # The service layer already gates this via availability(),
            # but be defensive — never make a call without a property.
            return FetchResult(rows=[], identifier=None, notes=[
                f"missing env {_ENV_PROPERTY_ID}; no fetch performed",
            ])

        client = self._build_client()
        request = self._build_request(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
        )
        response = client.run_report(request=request)

        rows: list[dict[str, object]] = []
        # Defensive iteration: response.rows / .metric_headers /
        # .dimension_headers should always exist on a real SDK
        # response, but we guard for mocks that omit them.
        dim_headers = list(getattr(response, "dimension_headers", []) or [])
        met_headers = list(getattr(response, "metric_headers", []) or [])
        for raw_row in getattr(response, "rows", []) or []:
            dim_values = [
                getattr(v, "value", "") for v in getattr(raw_row, "dimension_values", []) or []
            ]
            met_values = [
                getattr(v, "value", "") for v in getattr(raw_row, "metric_values", []) or []
            ]
            row: dict[str, object] = {}
            for i, header in enumerate(dim_headers):
                name = getattr(header, "name", f"dim_{i}")
                row[name] = dim_values[i] if i < len(dim_values) else ""
            for i, header in enumerate(met_headers):
                name = getattr(header, "name", f"metric_{i}")
                row[name] = met_values[i] if i < len(met_values) else ""
            rows.append(row)

        return FetchResult(rows=rows, identifier=property_id)

    # ---------- internals (lazy import boundary) ----------

    def _build_client(self):  # type: ignore[no-untyped-def]
        # Lazy import — keeps the module dependency-free until a
        # real fetch runs. Tests patch ``_build_client`` directly to
        # avoid pulling the SDK in.
        from google.analytics.data_v1beta import (  # type: ignore[import-not-found]
            BetaAnalyticsDataClient,
        )

        return BetaAnalyticsDataClient()

    def _build_request(
        self,
        *,
        property_id: str,
        start_date: date,
        end_date: date,
    ):  # type: ignore[no-untyped-def]
        from google.analytics.data_v1beta.types import (  # type: ignore[import-not-found]
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )

        return RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=n) for n in _REPORT_DIMENSIONS],
            metrics=[Metric(name=n) for n in _REPORT_METRICS],
            date_ranges=[
                DateRange(
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
            ],
        )


def _ga4_sdk_importable() -> bool:
    """Probe whether the GA4 SDK can be imported. Cached per process
    would be nice but the env can change between runs in tests, so
    we re-check each time."""

    try:
        import importlib

        importlib.import_module("google.analytics.data_v1beta")
    except Exception:  # noqa: BLE001 — any import-time failure means unavailable
        return False
    return True


__all__ = ["GA4ReadOnlyConnector"]
