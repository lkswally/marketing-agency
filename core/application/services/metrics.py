"""Metrics ingestion + analysis application services (architecture/
application-service-boundary, batch 2).

Migrates ``mkt import-metrics`` and ``mkt analyze-metrics``. Both are a
thin wrap over an already-complete domain boundary
(:class:`core.analytics.importer.AnalyticsImporter`,
:class:`core.analytics.analyzer.AnalyticsAnalyzer`) — persistence and
audit already happen inside those classes, migrated onto
``append_audit_event_atomic`` during job-execution-robustness GAP 1.
Kept in one module (not one file per command) because they are one
cohesive "metrics" concern, not two independent domains.

**LOCAL CLI INPUT vs SAFE APPLICATION INPUT (Phase 2).** ``import_metrics``
still accepts a local filesystem path, unlike ``intake`` (which was split
so the service takes an already-parsed dict). This is deliberate, not an
oversight: :meth:`AnalyticsImporter.import_file` is not "parse JSON then
call a service" the way ``ClientIntake.model_validate(dict)`` was — it is
itself the correct, pre-existing domain boundary that already owns real
file-format-specific parsing (``.csv`` via ``csv.DictReader`` needs a
file handle/text stream; ``.json`` via ``Path.read_text``; header-name
normalization; per-row numeric coercion; the file extension picks the
parser). Splitting "read bytes" from "parse" would mean either
duplicating that CSV/JSON-dispatch logic in the CLI, or changing
``core.analytics.importer``'s public contract to accept raw content +
an explicit format flag — a real change to domain code, out of scope
for a boundary-migration batch.

The accepted trade-off: a future HTTP adapter that wants to expose this
as an upload endpoint writes the uploaded bytes to a temporary file (a
standard, well-understood pattern for path-based processors) and passes
that path to this SAME service function — it is not blocked by this
service's shape, just one small step away from it. This is documented
here rather than silently preserved.
"""

from __future__ import annotations

import datetime as _datetime_mod
from pathlib import Path

from core.analytics import (
    AnalyticsAnalyzer,
    AnalyticsImporter,
    ImporterError,
    MetricSource,
    render_markdown_import_report,
    render_markdown_recommendations,
)
from core.memory import JsonFileMemory

from ..artifacts import OutputLayout, write_artifacts
from ..context import OperationContext
from ..result import ErrorCode, OperationResult

_IMPORT_MD_FILENAME = "analytics-import-report.md"
_IMPORT_JSON_FILENAME = "analytics-import-report.json"
_ANALYZE_MD_FILENAME = "analytics-recommendations.md"
_ANALYZE_JSON_FILENAME = "analytics-recommendations.json"


def import_metrics(
    ctx: OperationContext,
    *,
    source: str,
    file_path: str | Path,
    period_start: str | None = None,
    period_end: str | None = None,
    period_label: str | None = None,
) -> OperationResult:
    """Import a CSV/JSON metrics file for ``ctx.client_slug`` (LOCAL CLI
    INPUT: ``file_path`` — see module docstring), persist the resulting
    :class:`MetricsSnapshot` + :class:`AnalyticsImportReport` (done
    inside :class:`AnalyticsImporter`, including its own audit event),
    and write the Markdown + JSON report to ``ctx.outputs_root``.
    """
    try:
        parsed_source = MetricSource(source)
    except ValueError:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=(
                f"invalid source {source!r}; expected one of "
                f"{', '.join(s.value for s in MetricSource)}"
            ),
        )

    parsed_start, err = _parse_date(period_start, "period_start")
    if err is not None:
        return err
    parsed_end, err = _parse_date(period_end, "period_end")
    if err is not None:
        return err

    memory = JsonFileMemory(ctx.root)
    importer = AnalyticsImporter(memory=memory)
    try:
        report, snapshot = importer.import_file(
            client_slug=ctx.client_slug,
            source=parsed_source,
            file_path=file_path,
            period_start=parsed_start,
            period_end=parsed_end,
            period_label=period_label,
        )
    except ImporterError as e:
        return OperationResult.error_result(code=ErrorCode.INVALID_INPUT, message=str(e))

    files = {
        _IMPORT_MD_FILENAME: render_markdown_import_report(report),
        _IMPORT_JSON_FILENAME: report.to_json(indent=2),
    }
    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
        files=files,
        overwrite=True,
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code, message=write_err.message, remediation=write_err.remediation,
        )

    return OperationResult.ok_result(data={"report": report, "snapshot": snapshot}, artifacts=artifacts)


def analyze_metrics(ctx: OperationContext) -> OperationResult:
    """Analyze the persisted :class:`MetricsSnapshot` for
    ``ctx.client_slug`` and persist + write the resulting
    :class:`OptimizationRecommendationPack`."""
    memory = JsonFileMemory(ctx.root)
    analyzer = AnalyticsAnalyzer(memory=memory)
    try:
        pack = analyzer.analyze(ctx.client_slug)
    except ValueError as e:
        return OperationResult.error_result(code=ErrorCode.NOT_FOUND, message=str(e))
    analyzer.persist(pack)

    files = {
        _ANALYZE_MD_FILENAME: render_markdown_recommendations(pack),
        _ANALYZE_JSON_FILENAME: pack.to_json(indent=2),
    }
    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
        files=files,
        overwrite=True,
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code, message=write_err.message, remediation=write_err.remediation,
        )

    return OperationResult.ok_result(data=pack, artifacts=artifacts)


def _parse_date(
    value: str | None, field_name: str,
) -> tuple[_datetime_mod.date | None, OperationResult | None]:
    if not value:
        return None, None
    try:
        return _datetime_mod.date.fromisoformat(value), None
    except ValueError:
        return None, OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=f"invalid --{field_name.replace('_', '-')} {value!r}; expected YYYY-MM-DD",
        )


__all__ = ["analyze_metrics", "import_metrics"]
