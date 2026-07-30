"""CLI tests for ``mkt approvals list/show``, ``mkt approve``, ``mkt reject``
(MKT-11A, D-11.5)."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from cli.main import main
from core.approval.approval_pack import APPROVAL_PACK_KIND, SINGLETON_ID
from core.approval.models import ApprovalPack, ApprovalState
from core.memory import JsonFileMemory


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _seed_pack(
    root: Path, client: str, *, state: ApprovalState = ApprovalState.DRAFT,
) -> None:
    mem = JsonFileMemory(root)
    now = datetime.now(UTC)
    pack = ApprovalPack(
        client_slug=client, report_id="r1",
        report_contract_version="campaign-strategy-report.v1",
        created_at=now, updated_at=now, state=state,
    )
    mem.put(client, APPROVAL_PACK_KIND, SINGLETON_ID, pack.model_dump(mode="json"))


# ---------- approvals list ----------

def test_approvals_list_empty(tmp_path: Path) -> None:
    code, stdout = _run(["approvals", "list", "--root", str(tmp_path / "mem")])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 0
    assert payload["pending"] == []


def test_approvals_list_shows_pending(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme", state=ApprovalState.NEEDS_REVIEW)
    _seed_pack(tmp_path / "mem", "other-client", state=ApprovalState.APPROVED)
    code, stdout = _run(["approvals", "list", "--root", str(tmp_path / "mem")])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 1
    assert payload["pending"][0]["client_slug"] == "acme"


# ---------- approvals show ----------

def test_approvals_show_happy_path(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout = _run([
        "approvals", "show", "--client", "acme", "--root", str(tmp_path / "mem"),
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["client_slug"] == "acme"
    assert payload["state"] == "draft"


def test_approvals_show_not_found(tmp_path: Path) -> None:
    # MKT-11B: differentiated exit codes — NOT_FOUND is now 3, not the
    # generic 2 (see core.application.exit_codes.ExitCode).
    code, stdout = _run([
        "approvals", "show", "--client", "acme", "--root", str(tmp_path / "mem"),
    ])
    assert code == 3
    assert "no ApprovalPack" in stdout


# ---------- approve ----------

def test_approve_happy_path(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout = _run([
        "approve", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--actor", "lucas", "--notes", "ready to ship",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["state"] == "approved"
    assert payload["audit_event_id"] is not None
    assert payload["warnings"] == []


def test_approve_not_found_exits_2(tmp_path: Path) -> None:
    # MKT-11B: differentiated exit codes — NOT_FOUND is now 3, not the
    # generic 2 (see core.application.exit_codes.ExitCode). Function name
    # kept as-is to preserve this test's identity as a regression pin.
    code, stdout = _run([
        "approve", "--client", "acme", "--root", str(tmp_path / "mem"),
    ])
    assert code == 3
    assert "no ApprovalPack" in stdout


def test_approve_idempotent(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    argv = ["approve", "--client", "acme", "--root", str(tmp_path / "mem")]
    code1, _ = _run(argv)
    code2, stdout2 = _run(argv)
    assert code1 == 0
    assert code2 == 0
    payload = json.loads(stdout2)
    assert payload["warnings"]


def test_approve_after_reject_exits_2(tmp_path: Path) -> None:
    # MKT-11B: differentiated exit codes — INVALID_STATE_TRANSITION is
    # now 4, not the generic 2. Function name kept as-is (regression pin).
    _seed_pack(tmp_path / "mem", "acme")
    _run(["reject", "--client", "acme", "--root", str(tmp_path / "mem"), "--reason", "no"])
    code, stdout = _run(["approve", "--client", "acme", "--root", str(tmp_path / "mem")])
    assert code == 4
    assert "REJECTED" in stdout or "reject" in stdout.lower()


# ---------- reject ----------

def test_reject_happy_path(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout = _run([
        "reject", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--actor", "lucas", "--reason", "claims too risky",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["state"] == "rejected"
    assert payload["audit_event_id"] is not None


def test_reject_requires_reason_arg() -> None:
    """--reason is a required argparse argument — missing it is a
    parse-time SystemExit(2), not a runtime error."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        _run(["reject", "--client", "acme"])
    assert exc.value.code == 2


def test_reject_missing_pack_exits_2(tmp_path: Path) -> None:
    # MKT-11B: differentiated exit codes — NOT_FOUND is now 3, not the
    # generic 2. Function name kept as-is (regression pin).
    code, stdout = _run([
        "reject", "--client", "acme", "--root", str(tmp_path / "mem"), "--reason", "no data",
    ])
    assert code == 3
    assert "no ApprovalPack" in stdout


# ---------- multi-tenant ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    _seed_pack(tmp_path / "mem", "other-client")
    _run(["approve", "--client", "acme", "--root", str(tmp_path / "mem")])
    code, stdout = _run([
        "approvals", "show", "--client", "other-client", "--root", str(tmp_path / "mem"),
    ])
    payload = json.loads(stdout)
    assert payload["state"] == "draft"  # untouched by acme's approval


# ---------- audit ----------

def test_reject_writes_audit_event(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    _run([
        "reject", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--actor", "lucas", "--reason", "risky",
    ])
    audit_root = tmp_path / "mem" / "acme" / "audit"
    assert audit_root.exists()
    content = "\n".join(f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl"))
    assert "approval_pack" in content
    assert "rejected" in content
