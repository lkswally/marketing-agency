"""AnalyticsImporter — parse a CSV or JSON file into normalised MetricRows.

Pure stdlib (``csv`` + ``json``). No HTTP. No credential read. No
external service. The operator exports data manually from the
source platform and feeds the file path to ``mkt import-metrics``.

Each source has its own header convention; the importer is
forgiving — unknown columns are ignored, missing required columns
are rejected with a per-row reason, ``"3.5%"`` is coerced to
``0.035``, ``"1,234"`` is coerced to ``1234``.

Supported source / column conventions
-------------------------------------

``ga4``
    Columns (any order): ``date``, ``channel`` (optional;
    defaulted to ``"organic_search"``), ``page`` /
    ``page_path``, ``sessions``, ``users``, ``conversions``,
    ``bounce_rate``.

``search_console``
    Columns: ``date``, ``page`` / ``page_url``, ``query``,
    ``clicks``, ``impressions``, ``ctr``, ``position``.

``social``
    Columns: ``date``, ``channel``, ``post_id`` / ``post`` / ``url``,
    ``impressions``, ``engagement``, ``clicks``, ``reach``.

``email``
    Columns: ``date``, ``campaign_id`` / ``email_id``,
    ``sent``, ``opens``, ``clicks``, ``unsubscribes``.

``manual``
    Columns: ``date``, ``channel``, ``metric_name``, ``value``,
    ``content_ref``, ``dimension``. The freest format — every
    other source folds into ``MetricRow``, this one stays close
    to the model.

Each row from CSV produces ONE :class:`MetricRow` per numeric
column. For example a Search Console row with ``clicks=10``,
``impressions=1000``, ``ctr=0.01``, ``position=12.4`` produces
four metric rows (one per metric) so the analyzer can aggregate
them independently.
"""

from __future__ import annotations

import csv
import json
from datetime import date as _date
from datetime import datetime
from pathlib import Path

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory

from .models import (
    ANALYTICS_IMPORT_REPORT_KIND,
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    AnalyticsImportReport,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)


class ImporterError(RuntimeError):  # noqa: N818
    """Raised when the input file cannot be parsed at all (bad JSON,
    missing file, unsupported extension). Per-row errors are
    collected in the report instead of raised."""


# Column header normalisation. Header names from real GA4 exports
# vary (some use "Sessions" capitalised, some "sessions"); the
# importer lowercases everything before matching.
_GA4_COLUMNS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "total users": "users",
    "conversions": "conversions",
    "bounce_rate": "bounce_rate",
    "bounce rate": "bounce_rate",
}
_SC_COLUMNS: dict[str, str] = {
    "clicks": "clicks",
    "impressions": "impressions",
    "ctr": "ctr",
    "position": "position",
    "average position": "position",
}
_SOCIAL_COLUMNS: dict[str, str] = {
    "impressions": "impressions",
    "engagement": "engagement",
    "engagements": "engagement",
    "clicks": "clicks",
    "reach": "reach",
}
_EMAIL_COLUMNS: dict[str, str] = {
    "sent": "sent",
    "opens": "opens",
    "clicks": "clicks",
    "unsubscribes": "unsubscribes",
    "unsubscribed": "unsubscribes",
}


# ---------- public API ----------


class AnalyticsImporter:
    """Parse files and append to the per-client snapshot."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def import_file(
        self,
        *,
        client_slug: str,
        source: MetricSource,
        file_path: Path | str,
    ) -> tuple[AnalyticsImportReport, MetricsSnapshot]:
        path = Path(file_path)
        if not path.exists():
            raise ImporterError(f"file not found: {path}")

        raw_rows = _read_rows(path)
        new_rows, reasons = _normalise(raw_rows, source)

        snapshot = self._load_or_init_snapshot(client_slug)
        snapshot.rows.extend(new_rows)
        snapshot.updated_at = utcnow()

        report = AnalyticsImportReport(
            client_slug=client_slug,
            source=source,
            file_path=str(path),
            rows_imported=len(new_rows),
            rows_rejected=len(reasons),
            rejected_reasons=reasons[:50],  # cap to keep report bounded
            imported_at=utcnow(),
        )
        snapshot.last_import_id = report.import_id

        # Persist snapshot + report.
        self._memory.put(
            client_slug, METRICS_SNAPSHOT_KIND, SINGLETON_ID,
            snapshot.model_dump(mode="json"),
        )
        self._memory.put(
            client_slug, ANALYTICS_IMPORT_REPORT_KIND, SINGLETON_ID,
            report.model_dump(mode="json"),
        )

        # Audit event.
        prev = self._memory.last_audit_hash(client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="analytics_importer",
            occurred_at=utcnow(),
            client_slug=client_slug,
            payload={
                "analytics_import": {
                    "action": "imported",
                    "import_id": report.import_id,
                    "source": source.value,
                    "rows_imported": report.rows_imported,
                    "rows_rejected": report.rows_rejected,
                    "snapshot_id": snapshot.snapshot_id,
                    "snapshot_total_rows": snapshot.total_rows,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

        return report, snapshot

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


def import_and_persist(
    memory: Memory,
    *,
    client_slug: str,
    source: MetricSource,
    file_path: Path | str,
) -> tuple[AnalyticsImportReport, MetricsSnapshot]:
    return AnalyticsImporter(memory=memory).import_file(
        client_slug=client_slug, source=source, file_path=file_path
    )


# ---------- file parsing ----------


def _read_rows(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path)
    if suffix == ".json":
        return _read_json(path)
    raise ImporterError(
        f"unsupported file extension {suffix!r}; expected .csv or .json"
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file as a list of dicts. Defensive against
    ``DictReader``'s quirk of collecting overflow columns under a
    ``None`` key (as a list) — we ignore those and only keep
    explicit header→value pairs."""
    out: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return out
        for row in reader:
            cleaned: dict[str, str] = {}
            for k, v in row.items():
                if k is None or not isinstance(v, str):
                    # Either the overflow ``None`` bucket (list of extras)
                    # or a non-string value from a weird parser — skip.
                    continue
                cleaned[k.strip()] = v.strip()
            out.append(cleaned)
    return out


def _read_json(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ImporterError(f"invalid JSON: {e.msg}") from e
    if isinstance(data, dict):
        # Allow top-level dicts with a ``rows`` array (some exports
        # wrap their payload like that).
        data = (
            data["rows"]
            if "rows" in data and isinstance(data["rows"], list)
            else [data]
        )
    if not isinstance(data, list):
        raise ImporterError("JSON root must be a list or {\"rows\": [...]}")
    cleaned: list[dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        cleaned.append({str(k).strip(): str(v).strip() for k, v in entry.items()})
    return cleaned


# ---------- normalisation ----------


def _normalise(
    raw_rows: list[dict[str, str]], source: MetricSource
) -> tuple[list[MetricRow], list[str]]:
    out: list[MetricRow] = []
    reasons: list[str] = []
    if source is MetricSource.MANUAL:
        for i, raw in enumerate(raw_rows):
            try:
                out.append(_row_manual(raw))
            except _SkipRow as e:
                reasons.append(f"row {i + 1}: {e}")
    elif source is MetricSource.GA4:
        for i, raw in enumerate(raw_rows):
            try:
                out.extend(_rows_ga4(raw))
            except _SkipRow as e:
                reasons.append(f"row {i + 1}: {e}")
    elif source is MetricSource.SEARCH_CONSOLE:
        for i, raw in enumerate(raw_rows):
            try:
                out.extend(_rows_search_console(raw))
            except _SkipRow as e:
                reasons.append(f"row {i + 1}: {e}")
    elif source is MetricSource.SOCIAL:
        for i, raw in enumerate(raw_rows):
            try:
                out.extend(_rows_social(raw))
            except _SkipRow as e:
                reasons.append(f"row {i + 1}: {e}")
    elif source is MetricSource.EMAIL:
        for i, raw in enumerate(raw_rows):
            try:
                out.extend(_rows_email(raw))
            except _SkipRow as e:
                reasons.append(f"row {i + 1}: {e}")
    return out, reasons


class _SkipRow(Exception):  # noqa: N818
    """Raised by the per-source normalisers when a row should be
    rejected. Caught and added to the import report. The leading
    underscore signals an internal sentinel; ruff's N818 doesn't
    apply to private control-flow exceptions."""


def _lc_keys(d: dict[str, str]) -> dict[str, str]:
    return {(k or "").lower().strip(): v for k, v in d.items()}


def _parse_date(s: str) -> _date | None:
    s = (s or "").strip()
    if not s:
        return None
    # Common formats.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    is_percent = s.endswith("%")
    if is_percent:
        s = s[:-1].strip()
    s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if is_percent:
        v = v / 100.0
    return v


def _row_manual(raw: dict[str, str]) -> MetricRow:
    d = _lc_keys(raw)
    metric_name = (d.get("metric_name") or "").strip()
    if not metric_name:
        raise _SkipRow("missing metric_name")
    value = _parse_number(d.get("value", ""))
    if value is None:
        raise _SkipRow("missing or unparseable value")
    return MetricRow(
        source=MetricSource.MANUAL,
        event_date=_parse_date(d.get("date", "")),
        channel=(d.get("channel") or None) or None,
        content_ref=(d.get("content_ref") or None) or None,
        metric_name=metric_name,
        value=value,
        dimension=(d.get("dimension") or None) or None,
    )


def _rows_ga4(raw: dict[str, str]) -> list[MetricRow]:
    d = _lc_keys(raw)
    parsed_date = _parse_date(d.get("date", ""))
    channel = (d.get("channel") or "organic_search") or "organic_search"
    content_ref = (d.get("page") or d.get("page_path") or None) or None
    out: list[MetricRow] = []
    any_value = False
    for col, metric in _GA4_COLUMNS.items():
        if col not in d:
            continue
        value = _parse_number(d[col])
        if value is None:
            continue
        out.append(
            MetricRow(
                source=MetricSource.GA4,
                event_date=parsed_date,
                channel=channel,
                content_ref=content_ref,
                metric_name=metric,
                value=value,
            )
        )
        any_value = True
    if not any_value:
        raise _SkipRow("no GA4 numeric column found")
    return out


def _rows_search_console(raw: dict[str, str]) -> list[MetricRow]:
    d = _lc_keys(raw)
    parsed_date = _parse_date(d.get("date", ""))
    page = (d.get("page") or d.get("page_url") or None) or None
    query = (d.get("query") or None) or None
    out: list[MetricRow] = []
    any_value = False
    for col, metric in _SC_COLUMNS.items():
        if col not in d:
            continue
        value = _parse_number(d[col])
        if value is None:
            continue
        out.append(
            MetricRow(
                source=MetricSource.SEARCH_CONSOLE,
                event_date=parsed_date,
                channel="organic_search",
                content_ref=page,
                query=query,
                metric_name=metric,
                value=value,
            )
        )
        any_value = True
    if not any_value:
        raise _SkipRow("no Search Console numeric column found")
    return out


def _rows_social(raw: dict[str, str]) -> list[MetricRow]:
    d = _lc_keys(raw)
    parsed_date = _parse_date(d.get("date", ""))
    channel = (d.get("channel") or None) or None
    if not channel:
        raise _SkipRow("missing channel")
    content_ref = (
        d.get("post_id") or d.get("post") or d.get("url") or None
    ) or None
    out: list[MetricRow] = []
    any_value = False
    for col, metric in _SOCIAL_COLUMNS.items():
        if col not in d:
            continue
        value = _parse_number(d[col])
        if value is None:
            continue
        out.append(
            MetricRow(
                source=MetricSource.SOCIAL,
                event_date=parsed_date,
                channel=channel,
                content_ref=content_ref,
                metric_name=metric,
                value=value,
            )
        )
        any_value = True
    if not any_value:
        raise _SkipRow("no social numeric column found")
    return out


def _rows_email(raw: dict[str, str]) -> list[MetricRow]:
    d = _lc_keys(raw)
    parsed_date = _parse_date(d.get("date", ""))
    content_ref = (
        d.get("campaign_id") or d.get("email_id") or None
    ) or None
    if not content_ref:
        raise _SkipRow("missing campaign_id / email_id")
    out: list[MetricRow] = []
    any_value = False
    for col, metric in _EMAIL_COLUMNS.items():
        if col not in d:
            continue
        value = _parse_number(d[col])
        if value is None:
            continue
        out.append(
            MetricRow(
                source=MetricSource.EMAIL,
                event_date=parsed_date,
                channel="email",
                content_ref=content_ref,
                metric_name=metric,
                value=value,
            )
        )
        any_value = True
    if not any_value:
        raise _SkipRow("no email numeric column found")
    return out


__all__ = [
    "AnalyticsImporter",
    "ImporterError",
    "import_and_persist",
]
