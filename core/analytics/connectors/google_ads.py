"""Google Ads read-only adapter (MKT-6E).

Wraps ``google.ads.googleads.client.GoogleAdsClient`` and restricts
usage to a single read entry point: ``GoogleAdsService.search_stream``
with a GAQL query against the ``ad_group`` view. The SDK is
lazy-imported inside :meth:`availability` and :meth:`fetch` so the
module loads without the dependency installed and tests never
pull it in.

Environment variables (read at availability check, never logged):

- ``GOOGLE_ADS_DEVELOPER_TOKEN`` — developer token.
- ``GOOGLE_ADS_CLIENT_ID`` — OAuth client id.
- ``GOOGLE_ADS_CLIENT_SECRET`` — OAuth client secret.
- ``GOOGLE_ADS_REFRESH_TOKEN`` — long-lived OAuth refresh token.
- ``GOOGLE_ADS_LOGIN_CUSTOMER_ID`` — MCC / login customer id
  (digits only, no dashes).
- ``GOOGLE_ADS_CUSTOMER_ID`` — the customer id whose metrics are
  read. Persisted only as a hash-truncated fingerprint.

**Read-only strict.** This module deliberately does NOT import or
reference any Google Ads mutate service or ``Operation`` type. The
only SDK entry point used is ``GoogleAdsService.search_stream``.
The safety test suite grep-asserts that:

- No ``mutate_`` method name appears in source.
- No ``Operation`` type name appears in source.
- No service-name string starting with ``CampaignBudget``,
  ``Campaign``, ``AdGroup``, ``AdGroupAd`` etc. appears as a
  ``client.get_service(...)`` argument other than the read
  ``GoogleAdsService``.
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

_ENV_DEVELOPER_TOKEN = "GOOGLE_ADS_DEVELOPER_TOKEN"
_ENV_CLIENT_ID = "GOOGLE_ADS_CLIENT_ID"
_ENV_CLIENT_SECRET = "GOOGLE_ADS_CLIENT_SECRET"
_ENV_REFRESH_TOKEN = "GOOGLE_ADS_REFRESH_TOKEN"
_ENV_LOGIN_CUSTOMER_ID = "GOOGLE_ADS_LOGIN_CUSTOMER_ID"
_ENV_CUSTOMER_ID = "GOOGLE_ADS_CUSTOMER_ID"

_REQUIRED_ENV: tuple[str, ...] = (
    _ENV_DEVELOPER_TOKEN,
    _ENV_CLIENT_ID,
    _ENV_CLIENT_SECRET,
    _ENV_REFRESH_TOKEN,
    _ENV_CUSTOMER_ID,
)
"""``GOOGLE_ADS_LOGIN_CUSTOMER_ID`` is optional (non-MCC accounts
don't have it). Every other env var is required."""

# Read-only GAQL query at the ad_group level — broad enough to feed
# the analyzer's per-channel summaries, narrow enough to fit one
# round trip. Search-terms / keyword-level queries are deferred
# (P-6E.2).
_QUERY_AD_GROUP_METRICS = (
    "SELECT "
    "campaign.id, campaign.name, campaign.status, "
    "ad_group.id, ad_group.name, ad_group.status, "
    "segments.date, "
    "metrics.impressions, metrics.clicks, metrics.cost_micros, "
    "metrics.conversions, metrics.ctr, metrics.average_cpc, "
    "metrics.conversions_value, metrics.cost_per_conversion "
    "FROM ad_group "
    "WHERE segments.date BETWEEN '{start}' AND '{end}' "
    "AND campaign.status != 'REMOVED' "
    "AND ad_group.status != 'REMOVED'"
)


class GoogleAdsReadOnlyConnector(AnalyticsConnector):
    """Reads Google Ads metrics via ``GoogleAdsService.search_stream``."""

    def __init__(self, *, env: dict[str, str] | None = None) -> None:
        # ``env`` lets tests inject an isolated dict instead of the
        # real ``os.environ``. In production it is always ``None``
        # and the connector reads the live environment.
        self._env = env if env is not None else os.environ

    @property
    def source(self) -> str:
        return "google_ads"

    # ---------- availability ----------

    def availability(self) -> ConnectorAvailability:
        missing: list[str] = []
        for key in _REQUIRED_ENV:
            if not (self._env.get(key, "") or "").strip():
                missing.append(key)

        credentials_available = not missing
        creds_reason = ""
        if missing:
            creds_reason = "missing env " + ", ".join(missing)

        sdk_available = _ads_sdk_importable()
        sdk_reason = (
            "" if sdk_available else "google-ads SDK not installed"
        )

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
        """Run a single read-only GAQL query and return the raw rows.

        Exceptions from the SDK (network, permission, quota) are
        intentionally not caught here — the service layer wraps the
        call in try/except and produces a ``FAILED`` report.
        """

        customer_id = (self._env.get(_ENV_CUSTOMER_ID, "") or "").strip()
        if not customer_id:
            return FetchResult(rows=[], identifier=None, notes=[
                f"missing env {_ENV_CUSTOMER_ID}; no fetch performed",
            ])

        client = self._build_client()
        # ONLY service obtained from the client is the read service.
        # The safety pin grep-asserts this is the single
        # ``get_service`` argument used in this module.
        ga_service = client.get_service("GoogleAdsService")

        query = _QUERY_AD_GROUP_METRICS.format(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        rows: list[dict[str, object]] = []
        response = ga_service.search_stream(
            customer_id=customer_id, query=query,
        )
        for batch in response:
            for row in getattr(batch, "results", []) or []:
                rows.append(_row_to_dict(row))

        return FetchResult(rows=rows, identifier=customer_id)

    # ---------- internals (lazy import boundary) ----------

    def _build_client(self):  # type: ignore[no-untyped-def]
        # Lazy import — keeps the module dependency-free until a
        # real fetch runs. Tests patch ``_build_client`` directly to
        # avoid pulling the SDK in.
        from google.ads.googleads.client import (  # type: ignore[import-not-found]
            GoogleAdsClient,
        )

        config = {
            "developer_token": self._env.get(_ENV_DEVELOPER_TOKEN, ""),
            "client_id": self._env.get(_ENV_CLIENT_ID, ""),
            "client_secret": self._env.get(_ENV_CLIENT_SECRET, ""),
            "refresh_token": self._env.get(_ENV_REFRESH_TOKEN, ""),
            "use_proto_plus": True,
        }
        login_cid = (self._env.get(_ENV_LOGIN_CUSTOMER_ID, "") or "").strip()
        if login_cid:
            config["login_customer_id"] = login_cid
        return GoogleAdsClient.load_from_dict(config)


def _row_to_dict(row) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Convert a Google Ads response row (proto-plus object) into a
    plain dict the normalizer can consume. Defensive against
    SimpleNamespace mocks used in tests."""

    def _get(obj, dotted: str):  # type: ignore[no-untyped-def]
        current = obj
        for part in dotted.split("."):
            current = getattr(current, part, None)
            if current is None:
                return None
        return current

    return {
        "campaign.id": _get(row, "campaign.id"),
        "campaign.name": _get(row, "campaign.name"),
        "campaign.status": _stringify_enum(_get(row, "campaign.status")),
        "ad_group.id": _get(row, "ad_group.id"),
        "ad_group.name": _get(row, "ad_group.name"),
        "ad_group.status": _stringify_enum(_get(row, "ad_group.status")),
        "segments.date": _get(row, "segments.date"),
        "metrics.impressions": _get(row, "metrics.impressions"),
        "metrics.clicks": _get(row, "metrics.clicks"),
        "metrics.cost_micros": _get(row, "metrics.cost_micros"),
        "metrics.conversions": _get(row, "metrics.conversions"),
        "metrics.ctr": _get(row, "metrics.ctr"),
        "metrics.average_cpc": _get(row, "metrics.average_cpc"),
        "metrics.conversions_value": _get(row, "metrics.conversions_value"),
        "metrics.cost_per_conversion": _get(row, "metrics.cost_per_conversion"),
    }


def _stringify_enum(value) -> str | None:  # type: ignore[no-untyped-def]
    if value is None:
        return None
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)


def _ads_sdk_importable() -> bool:
    try:
        import importlib

        importlib.import_module("google.ads.googleads.client")
    except Exception:  # noqa: BLE001
        return False
    return True


__all__ = ["GoogleAdsReadOnlyConnector"]
