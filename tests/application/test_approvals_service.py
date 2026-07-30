"""Tests for the Approvals application service (MKT-11A, D-11.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services import approvals
from core.approval.approval_pack import APPROVAL_PACK_KIND, SINGLETON_ID
from core.approval.models import ApprovalPack, ApprovalState
from core.memory import JsonFileMemory


def _seed_pack(
    mem: JsonFileMemory, client_slug: str, *, state: ApprovalState = ApprovalState.DRAFT,
) -> ApprovalPack:
    now = datetime.now(UTC)
    pack = ApprovalPack(
        client_slug=client_slug,
        report_id="r1",
        report_contract_version="campaign-strategy-report.v1",
        created_at=now,
        updated_at=now,
        state=state,
    )
    mem.put(client_slug, APPROVAL_PACK_KIND, SINGLETON_ID, pack.model_dump(mode="json"))
    return pack


def _ctx(tmp_path: Path, client: str = "acme", actor: str = "reviewer-1") -> OperationContext:
    return OperationContext(client_slug=client, root=tmp_path / "mem", actor_id=actor)


# ---------- show ----------

def test_show_returns_pack(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.show(_ctx(tmp_path))
    assert result.ok
    assert result.data.client_slug == "acme"
    assert result.data.state is ApprovalState.DRAFT


def test_show_not_found(tmp_path: Path) -> None:
    result = approvals.show(_ctx(tmp_path))
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


# ---------- list_pending (cross-tenant) ----------

def test_list_pending_across_tenants(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme", state=ApprovalState.NEEDS_REVIEW)
    _seed_pack(mem, "other-client", state=ApprovalState.APPROVED)
    result = approvals.list_pending(root=tmp_path / "mem")
    assert result.ok
    slugs = {row.client_slug for row in result.data}
    assert slugs == {"acme"}  # APPROVED + not blocking is excluded


def test_list_pending_includes_blocked_even_if_terminal(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    now = datetime.now(UTC)
    blocked = ApprovalPack(
        client_slug="acme", report_id="r1",
        report_contract_version="campaign-strategy-report.v1",
        created_at=now, updated_at=now,
        state=ApprovalState.APPROVED, blocks_publish=True,
    )
    mem.put("acme", APPROVAL_PACK_KIND, SINGLETON_ID, blocked.model_dump(mode="json"))
    result = approvals.list_pending(root=tmp_path / "mem")
    assert len(result.data) == 1
    assert result.data[0].blocks_publish is True


def test_list_pending_empty_when_no_clients(tmp_path: Path) -> None:
    result = approvals.list_pending(root=tmp_path / "mem")
    assert result.ok
    assert result.data == []


# ---------- approve ----------

def test_approve_transitions_and_records_actor(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.approve(_ctx(tmp_path, actor="lucas"), notes="looks good")
    assert result.ok
    assert result.data.state is ApprovalState.APPROVED
    assert result.data.decision.reviewer == "lucas"
    assert result.data.decision.notes == "looks good"
    assert result.audit_event_id is not None


def test_approve_is_idempotent(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    ctx = _ctx(tmp_path)
    r1 = approvals.approve(ctx)
    r2 = approvals.approve(ctx)
    assert r1.ok and r2.ok
    assert r2.warnings
    assert r2.audit_event_id is None  # no new event on the idempotent no-op


def test_approve_after_reject_is_invalid_transition(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    ctx = _ctx(tmp_path)
    approvals.reject(ctx, reason="not ready")
    result = approvals.approve(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_STATE_TRANSITION


def test_approve_not_found(tmp_path: Path) -> None:
    result = approvals.approve(_ctx(tmp_path))
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


# ---------- reject ----------

def test_reject_requires_reason(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path), reason="")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_reject_whitespace_only_reason_rejected(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path), reason="   ")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_reject_transitions_and_records_reason(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path, actor="lucas"), reason="claims too risky")
    assert result.ok
    assert result.data.state is ApprovalState.REJECTED
    assert result.data.decision.reviewer == "lucas"
    assert result.data.decision.notes == "claims too risky"
    assert result.audit_event_id is not None


def test_reject_is_idempotent(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    ctx = _ctx(tmp_path)
    r1 = approvals.reject(ctx, reason="not ready")
    r2 = approvals.reject(ctx, reason="still not ready")
    assert r1.ok and r2.ok
    assert r2.warnings
    assert r2.audit_event_id is None


def test_reject_after_approve_is_invalid_transition(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    ctx = _ctx(tmp_path)
    approvals.approve(ctx)
    result = approvals.reject(ctx, reason="changed my mind")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_STATE_TRANSITION


def test_reject_not_found(tmp_path: Path) -> None:
    result = approvals.reject(_ctx(tmp_path), reason="no pack exists")
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


# ---------- audit trail ----------

def test_approve_audit_event_persisted(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    approvals.approve(_ctx(tmp_path, actor="lucas"))
    events = mem.read_audit_events("acme")
    assert len(events) == 1
    payload = events[0].payload["approval_pack"]
    assert payload["action"] == "approved"
    assert payload["reviewer"] == "lucas"


def test_reject_audit_event_persisted(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    approvals.reject(_ctx(tmp_path, actor="lucas"), reason="risky claims")
    events = mem.read_audit_events("acme")
    assert len(events) == 1
    payload = events[0].payload["approval_pack"]
    assert payload["action"] == "rejected"
    assert payload["reviewer"] == "lucas"


def test_idempotent_approve_does_not_append_audit_event(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    ctx = _ctx(tmp_path)
    approvals.approve(ctx)
    approvals.approve(ctx)
    events = mem.read_audit_events("acme")
    assert len(events) == 1  # only the real transition, not the no-op


# ---------- multi-tenant isolation ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    _seed_pack(mem, "other-client")
    approvals.approve(_ctx(tmp_path, "acme"))
    acme_result = approvals.show(_ctx(tmp_path, "acme"))
    other_result = approvals.show(_ctx(tmp_path, "other-client"))
    assert acme_result.data.state is ApprovalState.APPROVED
    assert other_result.data.state is ApprovalState.DRAFT
