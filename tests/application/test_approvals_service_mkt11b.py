"""MKT-11B additions to the Approvals application service — filters,
role authorization, --approval-id verification, correct audit_event_id,
corrupted-persistence handling, exit-code mapping.

Kept in a separate file from test_approvals_service.py (MKT-11A) so the
32 pre-existing regression pins there stay untouched and easy to diff.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.application import OperationContext, OperationRole
from core.application.exit_codes import ExitCode, exit_code_for
from core.application.result import ErrorCode
from core.application.services import approvals
from core.approval.approval_pack import APPROVAL_PACK_KIND, SINGLETON_ID
from core.approval.models import ApprovalPack, ApprovalState
from core.contracts import AuditEventType
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


def _ctx(
    tmp_path: Path,
    client: str = "acme",
    actor: str = "reviewer-1",
    role: OperationRole = OperationRole.OPERATOR,
) -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", actor_id=actor, role=role,
    )


# ---------- list_pending filters ----------

def test_list_pending_filters_by_client(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme", state=ApprovalState.NEEDS_REVIEW)
    _seed_pack(mem, "other-client", state=ApprovalState.NEEDS_REVIEW)
    result = approvals.list_pending(root=tmp_path / "mem", client_slug="acme")
    assert result.ok
    assert [r.client_slug for r in result.data] == ["acme"]


def test_list_pending_filters_by_status_bypasses_default_pending_filter(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme", state=ApprovalState.APPROVED)  # normally excluded
    result = approvals.list_pending(root=tmp_path / "mem", status=ApprovalState.APPROVED)
    assert result.ok
    assert len(result.data) == 1
    assert result.data[0].state is ApprovalState.APPROVED


def test_list_pending_status_filter_excludes_non_matching(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme", state=ApprovalState.DRAFT)
    _seed_pack(mem, "other-client", state=ApprovalState.NEEDS_REVIEW)
    result = approvals.list_pending(root=tmp_path / "mem", status=ApprovalState.NEEDS_REVIEW)
    assert [r.client_slug for r in result.data] == ["other-client"]


def test_list_pending_respects_limit(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    for slug in ("acme", "beta", "gamma"):
        _seed_pack(mem, slug, state=ApprovalState.NEEDS_REVIEW)
    result = approvals.list_pending(root=tmp_path / "mem", limit=2)
    assert len(result.data) == 2


def test_list_pending_client_and_status_combined(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme", state=ApprovalState.APPROVED)
    _seed_pack(mem, "other-client", state=ApprovalState.APPROVED)
    result = approvals.list_pending(
        root=tmp_path / "mem", client_slug="acme", status=ApprovalState.APPROVED,
    )
    assert len(result.data) == 1
    assert result.data[0].client_slug == "acme"


# ---------- --approval-id verification (D-11B.2) ----------

def test_show_approval_id_matches(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    pack = _seed_pack(mem, "acme")
    result = approvals.show(_ctx(tmp_path), approval_id=pack.pack_id)
    assert result.ok


def test_show_approval_id_mismatch_is_not_found(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.show(_ctx(tmp_path), approval_id="does-not-exist")
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_approve_approval_id_mismatch_blocks_transition(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.approve(_ctx(tmp_path), approval_id="wrong-id")
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND
    # No transition happened.
    reloaded = approvals.show(_ctx(tmp_path))
    assert reloaded.data.state is ApprovalState.DRAFT


def test_reject_approval_id_matches_succeeds(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    pack = _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path), reason="no", approval_id=pack.pack_id)
    assert result.ok


# ---------- role authorization (D-11.6) ----------

def test_viewer_cannot_approve(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.approve(_ctx(tmp_path, role=OperationRole.VIEWER))
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


def test_analyst_cannot_reject(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path, role=OperationRole.ANALYST), reason="no")
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


def test_approver_can_approve(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.approve(_ctx(tmp_path, role=OperationRole.APPROVER))
    assert result.ok


def test_admin_can_reject(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path, role=OperationRole.ADMIN), reason="policy")
    assert result.ok


def test_operator_can_approve_backward_compat(tmp_path: Path) -> None:
    """D-11B resolution: 'operator' remains authorized — the pre-11B
    contract already permitted it (see core/application/policies.py
    module docstring). This is what keeps the 32 MKT-11A regression
    pins green without modification."""
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.approve(_ctx(tmp_path, role=OperationRole.OPERATOR))
    assert result.ok


def test_viewer_permission_denied_before_state_check(tmp_path: Path) -> None:
    """Permission is checked before the pack even needs to exist —
    a viewer gets PERMISSION_DENIED, not NOT_FOUND, against a client
    with no pack at all."""
    result = approvals.approve(_ctx(tmp_path, role=OperationRole.VIEWER))
    assert not result.ok
    assert result.error.code is ErrorCode.PERMISSION_DENIED


# ---------- audit_event_id correctness (MKT-11A bug fix) ----------

def test_approve_audit_event_id_is_real_event_id_not_hash(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.approve(_ctx(tmp_path))
    assert result.ok
    events = mem.read_audit_events("acme")
    assert len(events) == 1
    assert result.audit_event_id == events[0].event_id
    assert result.audit_event_id != events[0].hash


def test_reject_audit_event_id_is_real_event_id_not_hash(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    result = approvals.reject(_ctx(tmp_path), reason="no")
    assert result.ok
    events = mem.read_audit_events("acme")
    assert result.audit_event_id == events[0].event_id


def test_audit_event_type_and_actor(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    approvals.approve(_ctx(tmp_path, actor="lucas"))
    events = mem.read_audit_events("acme")
    assert events[0].event_type is AuditEventType.NOTE
    assert events[0].actor == "approval_pack_builder"
    assert events[0].payload["approval_pack"]["reviewer"] == "lucas"


# ---------- corrupted / invalid persistence ----------

def test_show_corrupted_json_is_persistence_error(tmp_path: Path) -> None:
    mem_root = tmp_path / "mem"
    mem = JsonFileMemory(mem_root)
    _seed_pack(mem, "acme")
    pack_path = mem_root / "acme" / APPROVAL_PACK_KIND / f"{SINGLETON_ID}.json"
    pack_path.write_text("{not valid json", encoding="utf-8")
    result = approvals.show(_ctx(tmp_path))
    assert not result.ok
    assert result.error.code is ErrorCode.PERSISTENCE_ERROR


def test_show_schema_mismatch_is_persistence_error(tmp_path: Path) -> None:
    mem_root = tmp_path / "mem"
    mem = JsonFileMemory(mem_root)
    _seed_pack(mem, "acme")
    pack_path = mem_root / "acme" / APPROVAL_PACK_KIND / f"{SINGLETON_ID}.json"
    pack_path.write_text('{"totally": "wrong shape"}', encoding="utf-8")
    result = approvals.show(_ctx(tmp_path))
    assert not result.ok
    assert result.error.code is ErrorCode.PERSISTENCE_ERROR


def test_list_pending_skips_corrupted_entries_without_crashing(tmp_path: Path) -> None:
    mem_root = tmp_path / "mem"
    mem = JsonFileMemory(mem_root)
    _seed_pack(mem, "acme", state=ApprovalState.NEEDS_REVIEW)
    _seed_pack(mem, "broken-client", state=ApprovalState.NEEDS_REVIEW)
    broken_path = mem_root / "broken-client" / APPROVAL_PACK_KIND / f"{SINGLETON_ID}.json"
    broken_path.write_text("{not valid json", encoding="utf-8")
    result = approvals.list_pending(root=mem_root)
    assert result.ok
    assert [r.client_slug for r in result.data] == ["acme"]


# ---------- exit-code mapping ----------

def test_exit_code_for_not_found() -> None:
    assert exit_code_for(ErrorCode.NOT_FOUND) == ExitCode.NOT_FOUND == 3


def test_exit_code_for_invalid_state_transition() -> None:
    assert exit_code_for(ErrorCode.INVALID_STATE_TRANSITION) == ExitCode.INVALID_STATE_TRANSITION == 4


def test_exit_code_for_permission_denied() -> None:
    assert exit_code_for(ErrorCode.PERMISSION_DENIED) == ExitCode.PERMISSION_DENIED == 5


def test_exit_code_for_persistence_error() -> None:
    assert exit_code_for(ErrorCode.PERSISTENCE_ERROR) == ExitCode.PERSISTENCE_ERROR == 6


def test_exit_code_for_invalid_input() -> None:
    assert exit_code_for(ErrorCode.INVALID_INPUT) == ExitCode.INVALID_INPUT == 2


def test_exit_code_for_internal_falls_back_to_unexpected() -> None:
    assert exit_code_for(ErrorCode.INTERNAL) == ExitCode.UNEXPECTED == 70


# ---------- multi-tenant isolation of new features ----------

def test_role_check_is_per_context_not_global(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _seed_pack(mem, "acme")
    _seed_pack(mem, "other-client")
    viewer_result = approvals.approve(_ctx(tmp_path, "acme", role=OperationRole.VIEWER))
    approver_result = approvals.approve(
        _ctx(tmp_path, "other-client", role=OperationRole.APPROVER),
    )
    assert not viewer_result.ok
    assert approver_result.ok


# ---------- determinism ----------

def test_list_pending_deterministic_order(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    for slug in ("zeta", "alpha", "middle"):
        _seed_pack(mem, slug, state=ApprovalState.NEEDS_REVIEW)
    r1 = approvals.list_pending(root=tmp_path / "mem")
    r2 = approvals.list_pending(root=tmp_path / "mem")
    assert [r.client_slug for r in r1.data] == [r.client_slug for r in r2.data]
    assert [r.client_slug for r in r1.data] == ["alpha", "middle", "zeta"]
