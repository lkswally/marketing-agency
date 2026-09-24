"""Read-only analytics connector fetch application service (architecture/
application-service-boundary, batch 2).

Migrates ``mkt analytics-fetch`` (MKT-6D). Thin wrap over an
already-complete, already-security-conscious domain boundary:
:func:`core.analytics.connectors.resolve_connector` picks the concrete
connector (GA4 / Search Console / Google Ads / a forced dry-run stub) —
credential/SDK availability is read from ``os.environ`` entirely inside
the connector, never here — and :class:`AnalyticsFetchService` owns
fetch/normalize/persist/audit, including degrading to
``FetchStatus.SKIPPED``/``FAILED`` without raising when the connector
isn't ready or the upstream call fails.

**Secrets boundary (Phase 5/10).** This service never reads an
environment variable, never instantiates a provider SDK client, and
never sees a raw credential value or property/site identifier — it only
holds a :class:`AnalyticsFetchReport`, which the domain layer already
restricts to booleans (``sdk_available``/``credentials_available``) and
an 8-hex-char SHA-256 fingerprint (see
``core/analytics/connectors/service.py``'s
:func:`~core.analytics.connectors.service.fingerprint_identifier`) —
never the identifier itself. That report is exactly what lands in
``OperationResult.data``, in the persisted snapshot, and in the audit
event; nothing here adds a path where a secret could leak into any of
the three.
"""

from __future__ import annotations

from core.analytics.connectors import (
    DEFAULT_LOOKBACK_DAYS,
    AnalyticsFetchService,
    resolve_connector,
)
from core.analytics.connectors.service import write_report_outputs
from core.memory import JsonFileMemory

from ..context import OperationContext
from ..result import Artifact, ErrorCode, OperationResult


def fetch_analytics(
    ctx: OperationContext,
    *,
    source: str,
    dry_run: bool = False,
    lookback_days: int | None = None,
) -> OperationResult:
    """Run one read-only fetch for ``ctx.client_slug`` and write the
    Markdown + JSON report.

    Always OK unless ``source`` itself is unsupported — a SKIPPED or
    FAILED :class:`~core.analytics.connectors.models.FetchStatus` is a
    successful, structured outcome (degraded external data), not an
    :class:`OperationResult` error. This matches the CLI's long-standing
    "exit 0 including SKIPPED/FAILED — both are recorded, not crashes"
    contract.
    """
    memory = JsonFileMemory(ctx.root)
    try:
        connector = resolve_connector(source, dry_run=dry_run)
    except ValueError as e:
        return OperationResult.error_result(code=ErrorCode.INVALID_INPUT, message=str(e))

    service = AnalyticsFetchService(
        memory=memory,
        connector=connector,
        lookback_days=lookback_days or DEFAULT_LOOKBACK_DAYS,
    )
    report = service.run(client_slug=ctx.client_slug)

    md_path, json_path = write_report_outputs(report, outputs_dir=ctx.outputs_root)
    artifacts = [
        Artifact(path=md_path, kind="markdown"),
        Artifact(path=json_path, kind="json"),
    ]

    return OperationResult.ok_result(data=report, artifacts=artifacts)


__all__ = ["fetch_analytics"]
