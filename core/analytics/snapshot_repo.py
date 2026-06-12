"""Helpers for listing and loading time-ranged MetricsSnapshots (MKT-10B).

The ``"current"`` entity_id is the backward-compatible aggregate snapshot
that all existing callers use. Period-keyed snapshots use entity_ids of the
form ``"{source}-{YYYY-MM-DD}-{YYYY-MM-DD}"`` (see :func:`snapshot_entity_id`).

These helpers never write — they are read-only views over what the
:class:`~core.analytics.importer.AnalyticsImporter` and
:class:`~core.analytics.connectors.service.AnalyticsFetchService` persisted.
"""

from __future__ import annotations

from datetime import date

from core.memory import EntityNotFound, Memory

from .models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricSource,
    MetricsSnapshot,
)


def list_metric_snapshots(
    memory: Memory,
    client_slug: str,
    *,
    source: MetricSource | None = None,
) -> list[MetricsSnapshot]:
    """Return all period-keyed snapshots for *client_slug*, newest first.

    The ``"current"`` singleton is excluded — use :func:`load_metric_snapshot`
    with ``entity_id="current"`` to access it.

    Args:
        source: When provided, only snapshots whose ``source`` field matches
                are returned. ``None`` returns all period snapshots.

    Returns:
        Snapshots sorted by (period_start DESC, period_end DESC).
    """
    raws = memory.list(client_slug, METRICS_SNAPSHOT_KIND)
    out: list[MetricsSnapshot] = []
    for raw in raws:
        snap = MetricsSnapshot.model_validate(raw)
        if snap.period_start is None:
            continue  # skip the 'current' aggregate
        if source is not None and snap.source is not source:
            continue
        out.append(snap)
    out.sort(
        key=lambda s: (s.period_start or date.min, s.period_end or date.min),
        reverse=True,
    )
    return out


def load_metric_snapshot(
    memory: Memory,
    client_slug: str,
    *,
    entity_id: str,
) -> MetricsSnapshot:
    """Load a snapshot by its memory entity_id.

    Accepts both ``"current"`` and period-keyed ids such as
    ``"ga4-2024-06-01-2024-06-30"``.

    Raises:
        EntityNotFound: if no snapshot exists for this entity_id.
    """
    raw = memory.get(client_slug, METRICS_SNAPSHOT_KIND, entity_id)
    return MetricsSnapshot.model_validate(raw)


def latest_metric_snapshot(
    memory: Memory,
    client_slug: str,
    *,
    source: MetricSource | None = None,
) -> MetricsSnapshot | None:
    """Return the most recently updated snapshot for *client_slug*.

    - **No source filter** → returns ``"current"`` (the backward-compat
      aggregate). This is the same snapshot the analyzer uses.
    - **With source filter** → returns the newest period snapshot for that
      source. Falls back to ``"current"`` if no period snapshots exist.

    Returns ``None`` when no snapshot has been persisted at all.
    """
    if source is None:
        try:
            return load_metric_snapshot(memory, client_slug, entity_id=SINGLETON_ID)
        except EntityNotFound:
            return None

    period_snaps = list_metric_snapshots(memory, client_slug, source=source)
    if period_snaps:
        return period_snaps[0]  # already sorted newest-first

    try:
        return load_metric_snapshot(memory, client_slug, entity_id=SINGLETON_ID)
    except EntityNotFound:
        return None


__all__ = [
    "list_metric_snapshots",
    "load_metric_snapshot",
    "latest_metric_snapshot",
]
