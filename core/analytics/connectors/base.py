"""Abstract base for the MKT-6D read-only connectors.

The connector is a thin adapter with two responsibilities:

1. Tell the caller whether it is *available* (SDK installed +
   credentials present in the environment).
2. Produce a list of raw rows when fetched.

Normalisation into :class:`core.analytics.MetricRow` is done by
:mod:`core.analytics.connectors.normalizer`, not by the connector
itself, so each adapter stays narrow and easy to mock.

**Read-only contract.** The ABC only declares ``fetch`` —
deliberately not ``write`` / ``create`` / ``delete`` / ``update``.
Concrete subclasses MUST NOT add mutation methods. The safety test
suite grep-asserts this.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta

AVAILABILITY_OK = "ok"


@dataclass(frozen=True)
class ConnectorAvailability:
    """Why a connector is (un)available right now.

    Returned by :meth:`AnalyticsConnector.availability`. The
    operator never has to wonder *why* a fetch was skipped — the
    ``reason`` carries the human explanation.
    """

    sdk_available: bool
    credentials_available: bool
    reason: str
    """Free-form explanation. ``"ok"`` when both flags are true."""

    @property
    def is_ready(self) -> bool:
        return self.sdk_available and self.credentials_available


@dataclass
class FetchResult:
    """Raw result of a connector fetch — before normalisation.

    ``rows`` are *connector-native* shapes (dicts). The normalizer
    converts each shape into :class:`MetricRow`. ``identifier`` is
    the property id / site url the fetch ran against — the service
    layer hashes it before persisting.
    """

    rows: list[dict[str, object]] = field(default_factory=list)
    identifier: str | None = None
    notes: list[str] = field(default_factory=list)


class AnalyticsConnector(ABC):
    """Read-only adapter for one analytics source.

    Subclasses MUST implement :meth:`source`, :meth:`availability`
    and :meth:`fetch`. Subclasses MUST NOT add public methods that
    perform writes against the upstream service.
    """

    @property
    @abstractmethod
    def source(self) -> str:
        """One of :data:`core.analytics.connectors.models.SUPPORTED_SOURCES`."""

    @abstractmethod
    def availability(self) -> ConnectorAvailability:
        """Return whether the connector can run right now.

        Implementations must:

        - try the SDK import inside this method (lazy), never at
          module top level.
        - read environment variables, never accept credentials as
          method arguments.
        - never log the credential values themselves.
        """

    @abstractmethod
    def fetch(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> FetchResult:
        """Read data from the upstream service for the given date
        range. Must NOT mutate any remote state.

        Implementations should let exceptions from the SDK propagate
        — the service layer catches them and folds them into a
        ``FetchStatus.FAILED`` report.
        """


class DryRunConnector(AnalyticsConnector):
    """A connector that always reports unavailable.

    Used by the ``--dry-run`` flag and as a safe default when no
    real adapter has been wired. It never imports the SDK, never
    reads env vars and never makes a network call.
    """

    def __init__(self, source: str, *, reason: str = "dry-run mode") -> None:
        self._source = source
        self._reason = reason

    @property
    def source(self) -> str:
        return self._source

    def availability(self) -> ConnectorAvailability:
        return ConnectorAvailability(
            sdk_available=False,
            credentials_available=False,
            reason=self._reason,
        )

    def fetch(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> FetchResult:
        # Belt-and-braces: dry-run never calls anything. The service
        # layer is the one that checks availability first, but we
        # also guard here in case a caller bypasses the check.
        del start_date, end_date
        return FetchResult(rows=[], notes=[self._reason])


def default_lookback_window(today: date, lookback_days: int) -> tuple[date, date]:
    """Compute ``(start, end)`` dates for a rolling lookback window.

    ``end_date`` is the day before ``today`` (yesterday) because
    GA4 / Search Console aggregations for *today* are typically
    incomplete. ``start_date`` is ``end_date - (lookback_days - 1)``.
    """

    if lookback_days < 1:
        raise ValueError("lookback_days must be >= 1")
    end = today - timedelta(days=1)
    start = end - timedelta(days=lookback_days - 1)
    return start, end


__all__ = [
    "AVAILABILITY_OK",
    "AnalyticsConnector",
    "ConnectorAvailability",
    "DryRunConnector",
    "FetchResult",
    "default_lookback_window",
]
