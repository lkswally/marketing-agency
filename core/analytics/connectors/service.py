"""Service layer for the read-only connectors (MKT-6D).

Glues a connector + the normalizer + memory persistence + audit
trail into one entry point :class:`AnalyticsFetchService`. The
``mkt analytics-fetch`` CLI is a thin wrapper around this.

Responsibilities:

1. Choose a connector for ``source`` (real or :class:`DryRunConnector`).
2. Check availability. If not available → emit a
   ``FetchStatus.SKIPPED`` report and an audit ``fetch_skipped``
   event. **No upstream call.**
3. If available → call ``fetch``, catch any SDK exception
   (network / permission / quota) and emit ``FetchStatus.FAILED``
   without crashing.
4. Normalise rows. If a subset fails normalisation →
   ``FetchStatus.PARTIAL``; otherwise ``FetchStatus.OK``.
5. Append normalised rows to the per-client
   :class:`MetricsSnapshot`. Persist snapshot + fetch report.
6. Append an audit event with the *fingerprint* of the
   identifier — never the identifier itself.

**The service never logs / persists / returns the raw GA4 property
id or Search Console site url.** It hashes them via
:func:`fingerprint_identifier` and only the first 8 hex chars are
recorded.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricRow,
    MetricsSnapshot,
)
from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory

from .base import (
    AnalyticsConnector,
    DryRunConnector,
    default_lookback_window,
)
from .ga4 import GA4ReadOnlyConnector
from .google_ads import GoogleAdsReadOnlyConnector
from .models import (
    ANALYTICS_FETCH_REPORT_KIND,
    SUPPORTED_SOURCES,
    AnalyticsFetchReport,
    FetchStatus,
)
from .normalizer import (
    normalize_ga4_rows,
    normalize_google_ads_rows,
    normalize_search_console_rows,
)
from .search_console import SearchConsoleReadOnlyConnector

DEFAULT_LOOKBACK_DAYS = 28


def resolve_connector(
    source: str,
    *,
    dry_run: bool = False,
) -> AnalyticsConnector:
    """Return the concrete connector for ``source``.

    Pass ``dry_run=True`` to force a :class:`DryRunConnector` even
    when the real adapter would be available. Raises ``ValueError``
    on unsupported sources.
    """

    if source not in SUPPORTED_SOURCES:
        raise ValueError(
            f"unsupported source {source!r}: must be one of {SUPPORTED_SOURCES}"
        )
    if dry_run:
        return DryRunConnector(source, reason="dry-run flag set")
    if source == "ga4":
        return GA4ReadOnlyConnector()
    if source == "search_console":
        return SearchConsoleReadOnlyConnector()
    if source == "google_ads":
        return GoogleAdsReadOnlyConnector()
    # Unreachable, kept for explicitness.
    raise ValueError(f"no connector wired for source {source!r}")


def fingerprint_identifier(identifier: str | None) -> str | None:
    """SHA-256(identifier) truncated to 8 hex chars.

    Lets the operator correlate fetches across runs without leaking
    the GA4 property id or Search Console site url. ``None`` in,
    ``None`` out.
    """

    if not identifier:
        return None
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8]


class AnalyticsFetchService:
    """Orchestrates one ``mkt analytics-fetch`` invocation."""

    def __init__(
        self,
        *,
        memory: Memory,
        connector: AnalyticsConnector,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        today: date | None = None,
    ) -> None:
        self._memory = memory
        self._connector = connector
        self._lookback_days = lookback_days
        self._today = today or utcnow().date()

    # ---------- public API ----------

    def run(self, *, client_slug: str) -> AnalyticsFetchReport:
        started_at = utcnow()
        availability = self._connector.availability()

        if not availability.is_ready:
            return self._finish_skipped(
                client_slug=client_slug,
                reason=availability.reason,
                started_at=started_at,
                sdk_available=availability.sdk_available,
                credentials_available=availability.credentials_available,
                dry_run=isinstance(self._connector, DryRunConnector),
            )

        start_date, end_date = default_lookback_window(
            self._today, self._lookback_days
        )

        try:
            fetch_result = self._connector.fetch(
                start_date=start_date, end_date=end_date
            )
        except Exception as exc:  # noqa: BLE001 — capture SDK errors of any shape
            # The exception text could in theory contain a URL with
            # the site, so we sanitise: keep the type name only.
            error_type = type(exc).__name__
            return self._finish_failed(
                client_slug=client_slug,
                reason=f"connector raised {error_type}",
                started_at=started_at,
                sdk_available=availability.sdk_available,
                credentials_available=availability.credentials_available,
            )

        rows_fetched = len(fetch_result.rows)
        normalized, reasons = self._normalize(fetch_result.rows)
        rows_normalized = len(normalized)
        rows_rejected = len(reasons)
        identifier_fp = fingerprint_identifier(fetch_result.identifier)

        snapshot = self._append_to_snapshot(client_slug, normalized)
        status = FetchStatus.OK if rows_rejected == 0 else FetchStatus.PARTIAL

        report = self._persist_report(
            client_slug=client_slug,
            status=status,
            rows_fetched=rows_fetched,
            rows_normalized=rows_normalized,
            rows_rejected=rows_rejected,
            snapshot_id=snapshot.snapshot_id if snapshot else None,
            reason=None,
            sdk_available=True,
            credentials_available=True,
            dry_run=False,
            started_at=started_at,
            identifier_fp=identifier_fp,
            rejected_reasons=reasons[:50],
        )
        self._audit(
            client_slug,
            action="fetch_ok" if status is FetchStatus.OK else "fetch_partial",
            report=report,
        )
        return report

    # ---------- helpers ----------

    def _normalize(
        self, rows: list[dict[str, object]]
    ) -> tuple[list[MetricRow], list[str]]:
        if self._connector.source == "ga4":
            return normalize_ga4_rows(rows)
        if self._connector.source == "search_console":
            return normalize_search_console_rows(rows)
        if self._connector.source == "google_ads":
            return normalize_google_ads_rows(rows)
        return [], [f"no normaliser for source {self._connector.source!r}"]

    def _append_to_snapshot(
        self, client_slug: str, new_rows: list[MetricRow]
    ) -> MetricsSnapshot | None:
        if not new_rows:
            return None
        snapshot = self._load_or_init_snapshot(client_slug)
        snapshot.rows.extend(new_rows)
        snapshot.updated_at = utcnow()
        self._memory.put(
            client_slug,
            METRICS_SNAPSHOT_KIND,
            SINGLETON_ID,
            snapshot.model_dump(mode="json"),
        )
        return snapshot

    def _load_or_init_snapshot(self, client_slug: str) -> MetricsSnapshot:
        try:
            raw = self._memory.get(client_slug, METRICS_SNAPSHOT_KIND, SINGLETON_ID)
            return MetricsSnapshot.model_validate(raw)
        except EntityNotFound:
            now = utcnow()
            return MetricsSnapshot(
                client_slug=client_slug,
                rows=[],
                created_at=now,
                updated_at=now,
            )

    def _finish_skipped(
        self,
        *,
        client_slug: str,
        reason: str,
        started_at,
        sdk_available: bool,
        credentials_available: bool,
        dry_run: bool,
    ) -> AnalyticsFetchReport:
        report = self._persist_report(
            client_slug=client_slug,
            status=FetchStatus.SKIPPED,
            rows_fetched=0,
            rows_normalized=0,
            rows_rejected=0,
            snapshot_id=None,
            reason=reason,
            sdk_available=sdk_available,
            credentials_available=credentials_available,
            dry_run=dry_run,
            started_at=started_at,
            identifier_fp=None,
            rejected_reasons=[],
        )
        self._audit(client_slug, action="fetch_skipped", report=report)
        return report

    def _finish_failed(
        self,
        *,
        client_slug: str,
        reason: str,
        started_at,
        sdk_available: bool,
        credentials_available: bool,
    ) -> AnalyticsFetchReport:
        report = self._persist_report(
            client_slug=client_slug,
            status=FetchStatus.FAILED,
            rows_fetched=0,
            rows_normalized=0,
            rows_rejected=0,
            snapshot_id=None,
            reason=reason,
            sdk_available=sdk_available,
            credentials_available=credentials_available,
            dry_run=False,
            started_at=started_at,
            identifier_fp=None,
            rejected_reasons=[],
        )
        self._audit(client_slug, action="fetch_failed", report=report)
        return report

    def _persist_report(
        self,
        *,
        client_slug: str,
        status: FetchStatus,
        rows_fetched: int,
        rows_normalized: int,
        rows_rejected: int,
        snapshot_id: str | None,
        reason: str | None,
        sdk_available: bool,
        credentials_available: bool,
        dry_run: bool,
        started_at,
        identifier_fp: str | None,
        rejected_reasons: list[str],
    ) -> AnalyticsFetchReport:
        report = AnalyticsFetchReport(
            client_slug=client_slug,
            source=self._connector.source,
            status=status,
            rows_fetched=rows_fetched,
            rows_normalized=rows_normalized,
            rows_rejected=rows_rejected,
            snapshot_id=snapshot_id,
            reason=reason,
            sdk_available=sdk_available,
            credentials_available=credentials_available,
            dry_run=dry_run,
            lookback_days=self._lookback_days,
            started_at=started_at,
            finished_at=utcnow(),
            identifier_fingerprint=identifier_fp,
            rejected_reasons=rejected_reasons,
        )
        self._memory.put(
            client_slug,
            ANALYTICS_FETCH_REPORT_KIND,
            SINGLETON_ID,
            report.model_dump(mode="json"),
        )
        return report

    def _audit(
        self,
        client_slug: str,
        *,
        action: str,
        report: AnalyticsFetchReport,
    ) -> None:
        prev = self._memory.last_audit_hash(client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="analytics_fetch_service",
            occurred_at=utcnow(),
            client_slug=client_slug,
            payload={
                "analytics_fetch": {
                    "action": action,
                    "report_id": report.report_id,
                    "source": report.source,
                    "status": report.status.value,
                    "rows_fetched": report.rows_fetched,
                    "rows_normalized": report.rows_normalized,
                    "rows_rejected": report.rows_rejected,
                    "snapshot_id": report.snapshot_id,
                    "sdk_available": report.sdk_available,
                    "credentials_available": report.credentials_available,
                    "dry_run": report.dry_run,
                    "identifier_fingerprint": report.identifier_fingerprint,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)


def fetch_and_persist(
    memory: Memory,
    *,
    client_slug: str,
    source: str,
    dry_run: bool = False,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    today: date | None = None,
    connector: AnalyticsConnector | None = None,
) -> AnalyticsFetchReport:
    """Convenience entry point used by the CLI and by tests."""

    resolved = connector or resolve_connector(source, dry_run=dry_run)
    service = AnalyticsFetchService(
        memory=memory,
        connector=resolved,
        lookback_days=lookback_days,
        today=today,
    )
    return service.run(client_slug=client_slug)


# ---------- renderer ----------


def render_markdown_fetch_report(report: AnalyticsFetchReport) -> str:
    """Render an :class:`AnalyticsFetchReport` to Markdown."""

    lines: list[str] = []
    lines.append(f"# Analytics fetch report — `{report.source}`")
    lines.append("")
    lines.append(f"- **Client:** `{report.client_slug}`")
    lines.append(f"- **Status:** `{report.status.value}`")
    lines.append(f"- **Started:** `{report.started_at.isoformat()}`")
    lines.append(f"- **Finished:** `{report.finished_at.isoformat()}`")
    lines.append(f"- **Lookback days:** {report.lookback_days}")
    lines.append(f"- **SDK available:** {report.sdk_available}")
    lines.append(f"- **Credentials available:** {report.credentials_available}")
    lines.append(f"- **Dry-run:** {report.dry_run}")
    if report.identifier_fingerprint:
        lines.append(
            f"- **Identifier fingerprint:** `{report.identifier_fingerprint}` "
            "(SHA-256 truncated)"
        )
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Rows fetched: **{report.rows_fetched}**")
    lines.append(f"- Rows normalised: **{report.rows_normalized}**")
    lines.append(f"- Rows rejected: **{report.rows_rejected}**")
    if report.snapshot_id:
        lines.append(f"- Snapshot id: `{report.snapshot_id}`")
    lines.append("")
    if report.reason:
        lines.append("## Reason")
        lines.append("")
        lines.append(f"> {report.reason}")
        lines.append("")
    if report.rejected_reasons:
        lines.append("## Rejected rows")
        lines.append("")
        for r in report.rejected_reasons:
            lines.append(f"- {r}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "_Read-only fetch. No mutation of GA4 / Search Console. No "
        "credentials are persisted; sensitive identifiers are stored "
        "only as a hash fingerprint._"
    )
    lines.append("")
    return "\n".join(lines)


def write_report_outputs(
    report: AnalyticsFetchReport,
    *,
    outputs_dir: Path,
) -> tuple[Path, Path]:
    """Write the Markdown and JSON outputs for one fetch report."""

    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / f"analytics-fetch-report-{report.source}.md"
    json_path = outputs_dir / f"analytics-fetch-report-{report.source}.json"
    md_path.write_text(render_markdown_fetch_report(report), encoding="utf-8")
    json_path.write_text(report.to_json(indent=2), encoding="utf-8")
    return md_path, json_path


__all__ = [
    "AnalyticsFetchService",
    "DEFAULT_LOOKBACK_DAYS",
    "fetch_and_persist",
    "fingerprint_identifier",
    "render_markdown_fetch_report",
    "resolve_connector",
    "write_report_outputs",
]
