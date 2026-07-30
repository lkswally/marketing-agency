"""Tests for the Analytics snapshot read service (MKT-11A)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from core.analytics import METRICS_SNAPSHOT_KIND
from core.analytics.models import SINGLETON_ID as SNAPSHOT_SINGLETON_ID
from core.analytics.models import MetricRow, MetricSource, MetricsSnapshot, snapshot_entity_id
from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services import analytics
from core.domain.base import utcnow
from core.memory import JsonFileMemory


def _ctx(tmp_path: Path, client: str = "acme") -> OperationContext:
    return OperationContext(client_slug=client, root=tmp_path / "mem")


def _put_current(mem: JsonFileMemory, client: str) -> None:
    snap = MetricsSnapshot(
        client_slug=client,
        rows=[MetricRow(source=MetricSource.GA4, metric_name="sessions", value=10)],
        created_at=utcnow(), updated_at=utcnow(),
    )
    mem.put(client, METRICS_SNAPSHOT_KIND, SNAPSHOT_SINGLETON_ID, snap.model_dump(mode="json"))


def test_get_snapshot_current(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _put_current(mem, "acme")
    result = analytics.get_snapshot(_ctx(tmp_path))
    assert result.ok
    assert result.data.client_slug == "acme"


def test_get_snapshot_not_found(tmp_path: Path) -> None:
    result = analytics.get_snapshot(_ctx(tmp_path))
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_list_snapshots_period_scoped(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    src = MetricSource.GA4
    start, end = date(2026, 1, 1), date(2026, 1, 31)
    eid = snapshot_entity_id(src, start, end)
    snap = MetricsSnapshot(
        client_slug="acme", rows=[], created_at=utcnow(), updated_at=utcnow(),
        period_start=start, period_end=end, source=src,
    )
    mem.put("acme", METRICS_SNAPSHOT_KIND, eid, snap.model_dump(mode="json"))
    result = analytics.list_snapshots(_ctx(tmp_path))
    assert result.ok
    assert len(result.data) == 1


def test_list_snapshots_invalid_source(tmp_path: Path) -> None:
    result = analytics.list_snapshots(_ctx(tmp_path), source="not-a-source")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_get_latest_snapshot_falls_back_to_current(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _put_current(mem, "acme")
    result = analytics.get_latest_snapshot(_ctx(tmp_path), source="ga4")
    assert result.ok
    assert result.data.client_slug == "acme"


def test_get_latest_snapshot_none_when_empty(tmp_path: Path) -> None:
    result = analytics.get_latest_snapshot(_ctx(tmp_path))
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_multi_tenant_isolation(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _put_current(mem, "acme")
    other_result = analytics.get_snapshot(_ctx(tmp_path, "other-client"))
    assert not other_result.ok
    acme_result = analytics.get_snapshot(_ctx(tmp_path, "acme"))
    assert acme_result.ok
