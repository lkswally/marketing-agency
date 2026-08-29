"""Abstract base for MKT-10X read-only intelligence connectors.

Mirrors the pattern from :mod:`core.analytics.connectors.base` so the
two connector families are conceptually consistent.

**Read-only contract.** The ABC only declares ``fetch`` — no write,
create, delete, or update methods. Concrete subclasses MUST NOT add
mutation methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

AVAILABILITY_OK = "ok"


@dataclass(frozen=True)
class IntelligenceAvailability:
    """Whether a connector can run right now.

    ``sdk_available`` — the optional SDK import succeeded.
    ``credentials_available`` — required env vars are present.
    ``reason`` — human explanation; ``"ok"`` when fully ready.
    """

    sdk_available: bool
    credentials_available: bool
    reason: str

    @property
    def is_ready(self) -> bool:
        return self.sdk_available and self.credentials_available


@dataclass
class IntelligenceFetchResult:
    """Raw rows from an intelligence source before model mapping.

    ``rows`` are connector-native dicts. The caller maps them into
    ``TrendSignal``, ``CompetitorSignal``, etc.
    ``source`` names the connector that produced them.
    """

    rows: list[dict[str, object]] = field(default_factory=list)
    source: str = "unknown"
    notes: list[str] = field(default_factory=list)


class IntelligenceConnector(ABC):
    """Read-only adapter for one external intelligence source.

    Subclasses MUST implement ``source``, ``availability``, and ``fetch``.
    Subclasses MUST NOT add public methods that mutate remote state.
    """

    @property
    @abstractmethod
    def source(self) -> str:
        """Short identifier for this connector, e.g. ``"google_trends"``."""

    @abstractmethod
    def availability(self) -> IntelligenceAvailability:
        """Return current availability.

        Implementations must:
        - lazy-import optional SDKs inside this method, never at module top.
        - read env vars, never accept credentials as method arguments.
        - never log credential values.
        """

    @abstractmethod
    def fetch(
        self,
        *,
        keywords: list[str],
        start_date: date,
        end_date: date,
    ) -> IntelligenceFetchResult:
        """Fetch intelligence data. MUST NOT mutate remote state."""


class DryRunIntelligenceConnector(IntelligenceConnector):
    """Always-unavailable safe default. Never makes network calls.

    Used in tests, ``--dry-run`` mode, and whenever no real adapter
    has been wired.
    """

    def __init__(self, source: str, *, reason: str = "dry-run mode") -> None:
        self._source = source
        self._reason = reason

    @property
    def source(self) -> str:
        return self._source

    def availability(self) -> IntelligenceAvailability:
        return IntelligenceAvailability(
            sdk_available=False,
            credentials_available=False,
            reason=self._reason,
        )

    def fetch(
        self,
        *,
        keywords: list[str],
        start_date: date,
        end_date: date,
    ) -> IntelligenceFetchResult:
        del keywords, start_date, end_date
        return IntelligenceFetchResult(source=self._source, notes=[self._reason])


__all__ = [
    "AVAILABILITY_OK",
    "DryRunIntelligenceConnector",
    "IntelligenceAvailability",
    "IntelligenceConnector",
    "IntelligenceFetchResult",
]
