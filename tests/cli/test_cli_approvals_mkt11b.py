"""MKT-11B additions to the approvals CLI — filters, --approval-id,
--correlation-id, differentiated exit codes, clean stdout/stderr.

Kept separate from test_cli_approvals.py (MKT-11A) so its 32 pre-existing
regression pins stay untouched and easy to diff.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from cli.main import main
from core.approval.approval_pack import APPROVAL_PACK_KIND, SINGLETON_ID
from core.approval.models import ApprovalPack, ApprovalState


def _run(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err_capture = io.StringIO()
    import sys

    original_stderr = sys.stderr
    sys.stderr = err_capture
    try:
        code = main(argv, out=out)
    finally:
        sys.stderr = original_stderr
    return code, out.getvalue(), err_capture.getvalue()


def _seed_pack(
    root: Path, client: str, *, state: ApprovalState = ApprovalState.DRAFT,
) -> str:
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(root)
    now = datetime.now(UTC)
    pack = ApprovalPack(
        client_slug=client, report_id="r1",
        report_contract_version="campaign-strategy-report.v1",
        created_at=now, updated_at=now, state=state,
    )
    mem.put(client, APPROVAL_PACK_KIND, SINGLETON_ID, pack.model_dump(mode="json"))
    return pack.pack_id


# ---------- list filters ----------

def test_list_filters_by_client(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme", state=ApprovalState.NEEDS_REVIEW)
    _seed_pack(tmp_path / "mem", "other-client", state=ApprovalState.NEEDS_REVIEW)
    code, stdout, _ = _run([
        "approvals", "list", "--root", str(tmp_path / "mem"), "--client", "acme",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 1
    assert payload["pending"][0]["client_slug"] == "acme"


def test_list_filters_by_status(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme", state=ApprovalState.APPROVED)
    code, stdout, _ = _run([
        "approvals", "list", "--root", str(tmp_path / "mem"), "--status", "approved",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 1


def test_list_invalid_status_exits_2(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "approvals", "list", "--root", str(tmp_path / "mem"), "--status", "not-a-state",
    ])
    assert code == 2
    assert "invalid --status" in stdout


def test_list_respects_limit(tmp_path: Path) -> None:
    for slug in ("acme", "beta", "gamma"):
        _seed_pack(tmp_path / "mem", slug, state=ApprovalState.NEEDS_REVIEW)
    code, stdout, _ = _run([
        "approvals", "list", "--root", str(tmp_path / "mem"), "--limit", "1",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 1


# ---------- --approval-id ----------

def test_show_with_matching_approval_id(tmp_path: Path) -> None:
    pack_id = _seed_pack(tmp_path / "mem", "acme")
    code, stdout, _ = _run([
        "approvals", "show", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--approval-id", pack_id,
    ])
    assert code == 0


def test_show_with_mismatched_approval_id_exits_3(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout, _ = _run([
        "approvals", "show", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--approval-id", "wrong-id",
    ])
    assert code == 3


def test_approve_with_mismatched_approval_id_exits_3(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout, _ = _run([
        "approve", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--approval-id", "wrong-id",
    ])
    assert code == 3


# ---------- --correlation-id ----------

def test_approve_correlation_id_passthrough(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout, _ = _run([
        "approve", "--client", "acme", "--root", str(tmp_path / "mem"),
        "--correlation-id", "corr-123",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["correlation_id"] == "corr-123"


def test_reject_correlation_id_auto_generated_when_absent(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout, _ = _run([
        "reject", "--client", "acme", "--root", str(tmp_path / "mem"), "--reason", "no",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["correlation_id"]  # non-empty, auto-generated


# ---------- exit codes end-to-end ----------

def test_reject_empty_reason_exits_2(tmp_path: Path) -> None:
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout, _ = _run([
        "reject", "--client", "acme", "--root", str(tmp_path / "mem"), "--reason", "  ",
    ])
    assert code == 2


def test_show_persistence_error_exits_6(tmp_path: Path) -> None:
    mem_root = tmp_path / "mem"
    _seed_pack(mem_root, "acme")
    pack_path = mem_root / "acme" / APPROVAL_PACK_KIND / f"{SINGLETON_ID}.json"
    pack_path.write_text("{not valid json", encoding="utf-8")
    code, stdout, _ = _run([
        "approvals", "show", "--client", "acme", "--root", str(mem_root),
    ])
    assert code == 6


# ---------- stdout/stderr contract ----------

def test_approve_stdout_is_clean_json(tmp_path: Path) -> None:
    """stdout must parse as JSON with no leading/trailing noise —
    warnings and diagnostics belong on stderr."""
    _seed_pack(tmp_path / "mem", "acme")
    code, stdout, stderr = _run([
        "approve", "--client", "acme", "--root", str(tmp_path / "mem"),
    ])
    assert code == 0
    json.loads(stdout)  # raises if stdout has anything but the JSON payload


def test_list_stdout_is_clean_json(tmp_path: Path) -> None:
    code, stdout, _ = _run(["approvals", "list", "--root", str(tmp_path / "mem")])
    assert code == 0
    json.loads(stdout)


# ---------- portal untouched (safety re-check from this test module) ----------

def test_portal_package_not_imported_by_approvals_cli() -> None:
    """Structural pin: the approvals CLI path must not reach into the
    read-only portal package."""
    import cli.main as cli_main_module

    source = Path(cli_main_module.__file__).read_text(encoding="utf-8")
    # The approvals command block must not reference portal.* at all.
    assert "from portal" not in source
    assert "import portal" not in source
