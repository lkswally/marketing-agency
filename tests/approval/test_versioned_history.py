"""MKT-11E — versioned approval history: repository + acceptance-criteria
tests specific to this milestone (multi-approval coexistence, ordering,
job association, no silent invalidation by a later run).

Domain-level transition/idempotency/permission behaviour is unchanged and
already regression-pinned in test_approval_pack.py (MKT-3B) and
test_approvals_service*.py (MKT-11A/11B) — not duplicated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.approval import (
    APPROVAL_PACK_KIND,
    ApprovalPackBuilder,
    ApprovalState,
    get_latest_for_client,
    list_for_client,
    list_pending_for_client,
)
from core.approval import repository as approval_repository
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


@pytest.fixture
def demo_report(mem: JsonFileMemory):
    return StrategyPipeline(memory=mem).run_from_path(DEMO_BRIEF).report


def _build_and_persist(mem: JsonFileMemory, report, **kwargs):
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(report, **kwargs)
    builder.persist(pack)
    return pack


# ---------- unique identity, coexistence, no overwrite ----------

def test_each_build_gets_a_unique_id(mem: JsonFileMemory, demo_report) -> None:
    a = _build_and_persist(mem, demo_report)
    b = _build_and_persist(mem, demo_report)
    assert a.pack_id != b.pack_id


def test_two_approvals_for_same_client_coexist(mem: JsonFileMemory, demo_report) -> None:
    a = _build_and_persist(mem, demo_report)
    b = _build_and_persist(mem, demo_report)
    assert mem.exists(demo_report.client_slug, APPROVAL_PACK_KIND, a.pack_id)
    assert mem.exists(demo_report.client_slug, APPROVAL_PACK_KIND, b.pack_id)


def test_second_persist_does_not_overwrite_first(mem: JsonFileMemory, demo_report) -> None:
    a = _build_and_persist(mem, demo_report)
    _build_and_persist(mem, demo_report)
    builder = ApprovalPackBuilder(memory=mem)
    reloaded_a = builder.load(demo_report.client_slug, a.pack_id)
    assert reloaded_a.pack_id == a.pack_id
    assert reloaded_a.state is ApprovalState.DRAFT


def test_approving_one_does_not_affect_the_other(mem: JsonFileMemory, demo_report) -> None:
    a = _build_and_persist(mem, demo_report)
    b = _build_and_persist(mem, demo_report)
    builder = ApprovalPackBuilder(memory=mem)
    builder.approve(demo_report.client_slug, a.pack_id, reviewer="lucas")
    still_draft = builder.load(demo_report.client_slug, b.pack_id)
    assert still_draft.state is ApprovalState.DRAFT


# ---------- list ordering ----------

def test_list_for_client_orders_newest_first(mem: JsonFileMemory, demo_report) -> None:
    a = _build_and_persist(mem, demo_report)
    b = _build_and_persist(mem, demo_report)
    rows = list_for_client(mem, demo_report.client_slug)
    assert [r.pack_id for r in rows] == [b.pack_id, a.pack_id]


def test_list_for_client_filters_by_status(mem: JsonFileMemory, demo_report) -> None:
    a = _build_and_persist(mem, demo_report)
    _build_and_persist(mem, demo_report)
    builder = ApprovalPackBuilder(memory=mem)
    builder.approve(demo_report.client_slug, a.pack_id, reviewer="lucas")
    approved = list_for_client(mem, demo_report.client_slug, status=ApprovalState.APPROVED)
    assert [r.pack_id for r in approved] == [a.pack_id]


def test_list_for_client_filters_by_job_id(mem: JsonFileMemory, demo_report) -> None:
    _build_and_persist(mem, demo_report, job_id="job-1")
    b = _build_and_persist(mem, demo_report, job_id="job-2")
    rows = list_for_client(mem, demo_report.client_slug, job_id="job-2")
    assert [r.pack_id for r in rows] == [b.pack_id]


def test_get_latest_for_client_returns_newest(mem: JsonFileMemory, demo_report) -> None:
    _build_and_persist(mem, demo_report)
    b = _build_and_persist(mem, demo_report)
    latest = get_latest_for_client(mem, demo_report.client_slug)
    assert latest is not None
    assert latest.pack_id == b.pack_id


def test_get_latest_for_client_none_when_absent(mem: JsonFileMemory) -> None:
    assert get_latest_for_client(mem, "no-such-client") is None


def test_list_pending_for_client_excludes_terminal_non_blocking(
    mem: JsonFileMemory, demo_report,
) -> None:
    a = _build_and_persist(mem, demo_report)
    b = _build_and_persist(mem, demo_report)
    builder = ApprovalPackBuilder(memory=mem)
    builder.approve(demo_report.client_slug, a.pack_id, reviewer="lucas")
    pending = list_pending_for_client(mem, demo_report.client_slug)
    assert [p.pack_id for p in pending] == [b.pack_id]


# ---------- tenant isolation ----------

def test_list_for_client_is_tenant_isolated(mem: JsonFileMemory, demo_report) -> None:
    _build_and_persist(mem, demo_report)
    other_report = demo_report.model_copy(update={"client_slug": "other-client"})
    _build_and_persist(mem, other_report)
    acme_rows = list_for_client(mem, demo_report.client_slug)
    other_rows = list_for_client(mem, "other-client")
    assert len(acme_rows) == 1
    assert len(other_rows) == 1
    assert acme_rows[0].client_slug == demo_report.client_slug
    assert other_rows[0].client_slug == "other-client"


# ---------- job / correlation association ----------

def test_job_id_and_correlation_id_persisted(mem: JsonFileMemory, demo_report) -> None:
    pack = _build_and_persist(
        mem, demo_report, job_id="job-abc", correlation_id="corr-xyz",
    )
    reloaded = approval_repository.list_for_client(mem, demo_report.client_slug)[0]
    assert reloaded.pack_id == pack.pack_id
    assert reloaded.job_id == "job-abc"
    assert reloaded.correlation_id == "corr-xyz"


def test_audit_event_carries_job_id_when_present(mem: JsonFileMemory, demo_report) -> None:
    _build_and_persist(mem, demo_report, job_id="job-abc", correlation_id="corr-xyz")
    events = mem.read_audit_events(demo_report.client_slug)
    pack_events = [e for e in events if e.payload.get("approval_pack")]
    assert any(e.payload["approval_pack"].get("job_id") == "job-abc" for e in pack_events)
    assert any(
        e.payload["approval_pack"].get("correlation_id") == "corr-xyz" for e in pack_events
    )


def test_audit_event_omits_job_id_when_absent(mem: JsonFileMemory, demo_report) -> None:
    """Legacy (non-job) callers keep byte-identical payload shape — no
    null job_id/correlation_id keys injected when there is no job."""
    _build_and_persist(mem, demo_report)
    events = mem.read_audit_events(demo_report.client_slug)
    pack_events = [e for e in events if e.payload.get("approval_pack")]
    assert all("job_id" not in e.payload["approval_pack"] for e in pack_events)
    assert all("correlation_id" not in e.payload["approval_pack"] for e in pack_events)


# ---------- corrupted / unknown ----------

def test_load_unknown_approval_id_raises_entity_not_found(
    mem: JsonFileMemory, demo_report,
) -> None:
    from core.memory import EntityNotFound

    builder = ApprovalPackBuilder(memory=mem)
    with pytest.raises(EntityNotFound):
        builder.load(demo_report.client_slug, "does-not-exist")
