"""Tests for snapshot_repo helpers (MKT-10B)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.analytics import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricSource,
    MetricsSnapshot,
    latest_metric_snapshot,
    list_metric_snapshots,
    load_metric_snapshot,
    snapshot_entity_id,
    snapshot_id_from_period,
)
from core.memory import EntityNotFound, JsonFileMemory

# ---------- helper ----------

def _make_mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path / "mem")


def _put_snapshot(
    mem: JsonFileMemory,
    client_slug: str,
    entity_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source: MetricSource | None = None,
    period_label: str | None = None,
) -> MetricsSnapshot:
    from core.domain.base import utcnow

    now = utcnow()
    snap = MetricsSnapshot(
        client_slug=client_slug,
        rows=[],
        created_at=now,
        updated_at=now,
        period_start=period_start,
        period_end=period_end,
        source=source,
        period_label=period_label,
    )
    mem.put(client_slug, METRICS_SNAPSHOT_KIND, entity_id, snap.model_dump(mode="json"))
    return snap


# ---------- snapshot_entity_id ----------

def test_snapshot_entity_id_deterministic() -> None:
    src = MetricSource.GA4
    start = date(2024, 6, 1)
    end = date(2024, 6, 30)
    assert snapshot_entity_id(src, start, end) == "ga4-2024-06-01-2024-06-30"
    assert snapshot_entity_id(src, start, end) == snapshot_entity_id(src, start, end)


def test_snapshot_entity_id_differs_by_source() -> None:
    start = date(2024, 6, 1)
    end = date(2024, 6, 30)
    assert snapshot_entity_id(MetricSource.GA4, start, end) != snapshot_entity_id(
        MetricSource.SEARCH_CONSOLE, start, end
    )


def test_snapshot_entity_id_differs_by_period() -> None:
    src = MetricSource.GA4
    a = snapshot_entity_id(src, date(2024, 6, 1), date(2024, 6, 30))
    b = snapshot_entity_id(src, date(2024, 7, 1), date(2024, 7, 31))
    assert a != b


# ---------- snapshot_id_from_period ----------

def test_snapshot_id_from_period_deterministic() -> None:
    src = MetricSource.GA4
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    assert snapshot_id_from_period(src, start, end) == snapshot_id_from_period(
        src, start, end
    )


def test_snapshot_id_from_period_32_chars() -> None:
    sid = snapshot_id_from_period(MetricSource.GA4, date(2024, 6, 1), date(2024, 6, 30))
    assert len(sid) == 32


def test_snapshot_id_from_period_differs_from_entity_id() -> None:
    src = MetricSource.GA4
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    assert snapshot_id_from_period(src, start, end) != snapshot_entity_id(
        src, start, end
    )


# ---------- load_metric_snapshot ----------

def test_load_metric_snapshot_current(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    _put_snapshot(mem, "acme", SINGLETON_ID)
    snap = load_metric_snapshot(mem, "acme", entity_id=SINGLETON_ID)
    assert snap.client_slug == "acme"
    assert snap.period_start is None


def test_load_metric_snapshot_period_key(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    src = MetricSource.GA4
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    eid = snapshot_entity_id(src, start, end)
    _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)
    snap = load_metric_snapshot(mem, "acme", entity_id=eid)
    assert snap.period_start == start
    assert snap.source is src


def test_load_metric_snapshot_missing_raises(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    with pytest.raises(EntityNotFound):
        load_metric_snapshot(mem, "acme", entity_id="nonexistent")


# ---------- list_metric_snapshots ----------

def test_list_excludes_current(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    _put_snapshot(mem, "acme", SINGLETON_ID)
    assert list_metric_snapshots(mem, "acme") == []


def test_list_returns_period_snapshots(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    src = MetricSource.GA4
    for month in (6, 7):
        start = date(2024, month, 1)
        end = date(2024, month, 30)
        eid = snapshot_entity_id(src, start, end)
        _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)
    snaps = list_metric_snapshots(mem, "acme")
    assert len(snaps) == 2


def test_list_sorted_newest_first(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    src = MetricSource.GA4
    for month in (6, 7, 8):
        start = date(2024, month, 1)
        end = date(2024, month, 30)
        eid = snapshot_entity_id(src, start, end)
        _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)
    snaps = list_metric_snapshots(mem, "acme")
    starts = [s.period_start for s in snaps]
    assert starts == sorted(starts, reverse=True)


def test_list_filters_by_source(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    for src in (MetricSource.GA4, MetricSource.SEARCH_CONSOLE):
        eid = snapshot_entity_id(src, start, end)
        _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)
    ga4_only = list_metric_snapshots(mem, "acme", source=MetricSource.GA4)
    assert len(ga4_only) == 1
    assert ga4_only[0].source is MetricSource.GA4


def test_list_empty_when_no_snapshots(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    assert list_metric_snapshots(mem, "acme") == []


# ---------- latest_metric_snapshot ----------

def test_latest_no_source_returns_current(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    _put_snapshot(mem, "acme", SINGLETON_ID)
    snap = latest_metric_snapshot(mem, "acme")
    assert snap is not None
    assert snap.period_start is None


def test_latest_no_source_returns_none_when_missing(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    assert latest_metric_snapshot(mem, "acme") is None


def test_latest_with_source_returns_period_snapshot(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    src = MetricSource.GA4
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    eid = snapshot_entity_id(src, start, end)
    _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)
    snap = latest_metric_snapshot(mem, "acme", source=src)
    assert snap is not None
    assert snap.period_start == start


def test_latest_with_source_falls_back_to_current(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    _put_snapshot(mem, "acme", SINGLETON_ID)
    snap = latest_metric_snapshot(mem, "acme", source=MetricSource.GA4)
    assert snap is not None
    assert snap.period_start is None  # 'current' fallback


def test_latest_with_source_picks_newest_period(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    src = MetricSource.GA4
    for month in (5, 6, 7):
        start = date(2024, month, 1)
        end = date(2024, month, 30)
        eid = snapshot_entity_id(src, start, end)
        _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)
    snap = latest_metric_snapshot(mem, "acme", source=src)
    assert snap is not None
    assert snap.period_start == date(2024, 7, 1)


def test_latest_with_source_none_when_nothing(tmp_path: Path) -> None:
    mem = _make_mem(tmp_path)
    assert latest_metric_snapshot(mem, "acme", source=MetricSource.GA4) is None


# ---------- dual-write: current not overwritten by period import ----------

def test_period_import_does_not_replace_current(tmp_path: Path) -> None:
    """Verify both current and period entities coexist independently."""
    mem = _make_mem(tmp_path)
    _put_snapshot(mem, "acme", SINGLETON_ID)
    src = MetricSource.GA4
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    eid = snapshot_entity_id(src, start, end)
    _put_snapshot(mem, "acme", eid, period_start=start, period_end=end, source=src)

    current = load_metric_snapshot(mem, "acme", entity_id=SINGLETON_ID)
    period = load_metric_snapshot(mem, "acme", entity_id=eid)
    assert current.period_start is None
    assert period.period_start == start


def test_re_import_same_period_uses_same_entity_id(tmp_path: Path) -> None:
    """Same (source, period) always maps to same entity_id — idempotent."""
    src = MetricSource.GA4
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    eid1 = snapshot_entity_id(src, start, end)
    eid2 = snapshot_entity_id(src, start, end)
    assert eid1 == eid2
