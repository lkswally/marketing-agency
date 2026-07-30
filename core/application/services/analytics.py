"""Analytics snapshot read services (MKT-11A).

Read-only. There is no CLI equivalent to preserve — this exposes the
MKT-10B ``snapshot_repo`` helpers (``list_metric_snapshots`` /
``load_metric_snapshot`` / ``latest_metric_snapshot``) through the
application layer for the first time, so the future Control Center's
Analytics module has something to call without touching
``core.memory`` or ``core.analytics`` directly.
"""

from __future__ import annotations

from core.analytics import (
    SINGLETON_ID,
    MetricSource,
    latest_metric_snapshot,
    list_metric_snapshots,
    load_metric_snapshot,
)
from core.memory import EntityNotFound, JsonFileMemory

from ..context import OperationContext
from ..result import ErrorCode, OperationResult


def list_snapshots(
    ctx: OperationContext, *, source: str | None = None,
) -> OperationResult:
    """List period-scoped snapshots for the tenant (excludes ``"current"``).

    ``source`` filters to a single :class:`MetricSource` value when given.
    """
    memory = JsonFileMemory(ctx.root)
    parsed_source: MetricSource | None = None
    if source:
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
    snapshots = list_metric_snapshots(memory, ctx.client_slug, source=parsed_source)
    return OperationResult.ok_result(data=snapshots)


def get_snapshot(
    ctx: OperationContext, *, entity_id: str = SINGLETON_ID,
) -> OperationResult:
    """Load one snapshot by entity id (``"current"`` by default)."""
    memory = JsonFileMemory(ctx.root)
    try:
        snapshot = load_metric_snapshot(memory, ctx.client_slug, entity_id=entity_id)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no MetricsSnapshot {entity_id!r} for client {ctx.client_slug!r}",
            remediation="run `mkt import-metrics` or `mkt analytics-fetch` first",
        )
    return OperationResult.ok_result(data=snapshot)


def get_latest_snapshot(
    ctx: OperationContext, *, source: str | None = None,
) -> OperationResult:
    """Return the most recently updated snapshot — 'current' when no
    source filter is given, else the newest period snapshot for that
    source (falling back to 'current')."""
    memory = JsonFileMemory(ctx.root)
    parsed_source: MetricSource | None = None
    if source:
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
    snapshot = latest_metric_snapshot(memory, ctx.client_slug, source=parsed_source)
    if snapshot is None:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no MetricsSnapshot for client {ctx.client_slug!r}",
            remediation="run `mkt import-metrics` or `mkt analytics-fetch` first",
        )
    return OperationResult.ok_result(data=snapshot)


__all__ = ["get_latest_snapshot", "get_snapshot", "list_snapshots"]
