"""Pydantic models for the GA4 / Search Console connectors (MKT-6D).

One contract:

- ``analytics-fetch-report.v1`` — :class:`AnalyticsFetchReport`
  documenting one ``mkt analytics-fetch`` invocation, including
  the connector source, status, normalized row counts and the
  hash-truncated fingerprint of sensitive identifiers (property
  id / site url) so the operation is auditable without leaking
  credentials.

No credential / token / api_key / url field appears on any
persisted model. Sensitive identifiers are stored exclusively
as hash-truncated fingerprints.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

ANALYTICS_FETCH_REPORT_VERSION = "analytics-fetch-report.v1"
ANALYTICS_FETCH_REPORT_KIND = "analytics_fetch_report"

SUPPORTED_SOURCES: tuple[str, ...] = ("ga4", "search_console", "google_ads")


class FetchStatus(StrEnum):
    """High-level fetch outcome."""

    OK = "ok"
    """Connector ran end-to-end and produced normalised rows."""

    SKIPPED = "skipped"
    """Connector intentionally did not call the upstream service —
    typically because credentials or the SDK are not available, or
    ``--dry-run`` was passed. Not an error."""

    PARTIAL = "partial"
    """Fetch succeeded but a subset of rows could not be normalised."""

    FAILED = "failed"
    """Connector attempted the upstream call but a captured error
    occurred (network, permission, quota). The system did not
    crash — the failure is recorded."""


class AnalyticsFetchReport(DomainModel):
    """One ``mkt analytics-fetch`` invocation.

    Persisted via :class:`core.memory.Memory` under
    ``ANALYTICS_FETCH_REPORT_KIND`` with singleton id ``"current"``.
    """

    contract_version: Literal["analytics-fetch-report.v1"] = (
        ANALYTICS_FETCH_REPORT_VERSION
    )
    report_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    source: Annotated[str, Field(min_length=1, max_length=32)]
    """One of :data:`SUPPORTED_SOURCES`."""

    status: FetchStatus
    rows_fetched: int = Field(ge=0)
    rows_normalized: int = Field(ge=0)
    rows_rejected: int = Field(ge=0)
    snapshot_id: str | None = None
    """Set when the fetch produced rows that were appended to the
    :class:`MetricsSnapshot`. ``None`` for skipped / failed."""

    reason: str | None = Field(default=None, max_length=400)
    """Free-form explanation of a skipped / failed / partial run."""

    sdk_available: bool
    credentials_available: bool
    dry_run: bool = False

    lookback_days: int = Field(ge=1, le=365)
    started_at: datetime
    finished_at: datetime

    identifier_fingerprint: str | None = Field(default=None, max_length=32)
    """First 8 hex chars of SHA-256(identifier). Lets the operator
    correlate fetches across runs without leaking the GA4 property
    id or Search Console site url. ``None`` when no identifier was
    configured."""

    rejected_reasons: list[str] = Field(default_factory=list)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in SUPPORTED_SOURCES:
            raise ValueError(
                f"unsupported source {v!r}: must be one of {SUPPORTED_SOURCES}"
            )
        return v

    @field_validator("started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v


__all__ = [
    "ANALYTICS_FETCH_REPORT_KIND",
    "ANALYTICS_FETCH_REPORT_VERSION",
    "AnalyticsFetchReport",
    "FetchStatus",
    "SUPPORTED_SOURCES",
]
