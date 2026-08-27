"""CLI tests for ``mkt jobs submit/run/list/show/cancel`` (MKT-11C)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from cli.main import main


def _run(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err_capture = io.StringIO()
    original_stderr = sys.stderr
    sys.stderr = err_capture
    try:
        code = main(argv, out=out)
    finally:
        sys.stderr = original_stderr
    return code, out.getvalue(), err_capture.getvalue()


# ---------- submit ----------

def test_submit_happy_path(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", "demo.echo",
        "--params", '{"message": "hi"}', "--root", str(tmp_path / "mem"),
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["state"] == "queued"
    assert payload["operation"] == "demo.echo"


def test_submit_invalid_json_params_exits_2(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", "demo.echo",
        "--params", "{not json", "--root", str(tmp_path / "mem"),
    ])
    assert code == 2
    assert "invalid --params" in stdout


def test_submit_unknown_operation_exits_2(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", "nope",
        "--params", "{}", "--root", str(tmp_path / "mem"),
    ])
    assert code == 2


def test_submit_with_run_flag_executes_immediately(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", "demo.echo",
        "--params", '{"message": "hi"}', "--root", str(tmp_path / "mem"), "--run",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["state"] == "completed"


def test_submit_with_run_flag_and_failure_exits_7(tmp_path: Path) -> None:
    code, stdout, stderr = _run([
        "jobs", "submit", "--client", "acme", "--operation", "demo.fail",
        "--params", '{"reason": "boom"}', "--root", str(tmp_path / "mem"), "--run",
    ])
    assert code == 7
    payload = json.loads(stdout)  # stdout must still be clean JSON
    assert payload["state"] == "failed"
    assert payload["error"]["message"] == "boom"
    assert "boom" in stderr


def test_submit_default_params_empty_dict(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", "demo.fail",
        "--root", str(tmp_path / "mem"),
    ])
    # demo.fail requires 'reason' — omitted --params means {} which fails validation.
    assert code == 2


# ---------- run ----------

def _submit(root: str, operation: str = "demo.echo", params: str = '{"message": "hi"}') -> str:
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", operation,
        "--params", params, "--root", root,
    ])
    assert code == 0
    return json.loads(stdout)["job_id"]


def test_run_happy_path(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root)
    code, stdout, _ = _run(["jobs", "run", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 0
    assert json.loads(stdout)["state"] == "completed"


def test_run_idempotent_warning_on_stderr(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root)
    _run(["jobs", "run", "--client", "acme", "--job-id", job_id, "--root", root])
    code, stdout, stderr = _run(["jobs", "run", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 0
    json.loads(stdout)  # still clean JSON
    assert "WARNING" in stderr


def test_run_not_found_exits_3(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "run", "--client", "acme", "--job-id", "nope", "--root", str(tmp_path / "mem"),
    ])
    assert code == 3


def test_run_failed_exits_7_with_clean_json(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root, operation="demo.fail", params='{"reason": "boom"}')
    code, stdout, stderr = _run(["jobs", "run", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 7
    payload = json.loads(stdout)
    assert payload["state"] == "failed"
    assert "boom" in stderr


def test_run_waiting_approval(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root, operation="demo.needs_approval", params='{"reason": "risky"}')
    code, stdout, _ = _run(["jobs", "run", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 0
    assert json.loads(stdout)["state"] == "waiting_approval"


# ---------- list ----------

def test_list_empty(tmp_path: Path) -> None:
    code, stdout, _ = _run(["jobs", "list", "--client", "acme", "--root", str(tmp_path / "mem")])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 0


def test_list_shows_submitted_jobs(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    _submit(root)
    _submit(root)
    code, stdout, _ = _run(["jobs", "list", "--client", "acme", "--root", root])
    assert code == 0
    assert json.loads(stdout)["count"] == 2


def test_list_filters_by_status(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    j1 = _submit(root)
    _submit(root)
    _run(["jobs", "run", "--client", "acme", "--job-id", j1, "--root", root])
    code, stdout, _ = _run([
        "jobs", "list", "--client", "acme", "--root", root, "--status", "completed",
    ])
    assert json.loads(stdout)["count"] == 1


def test_list_respects_limit(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    for _ in range(3):
        _submit(root)
    code, stdout, _ = _run(["jobs", "list", "--client", "acme", "--root", root, "--limit", "1"])
    assert json.loads(stdout)["count"] == 1


# ---------- show ----------

def test_show_happy_path(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root)
    code, stdout, _ = _run(["jobs", "show", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 0
    assert json.loads(stdout)["job_id"] == job_id


def test_show_not_found_exits_3(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "show", "--client", "acme", "--job-id", "nope", "--root", str(tmp_path / "mem"),
    ])
    assert code == 3


# ---------- cancel ----------

def test_cancel_queued(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root)
    code, stdout, _ = _run(["jobs", "cancel", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 0
    assert json.loads(stdout)["state"] == "cancelled"


def test_cancel_running_exits_4(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    from core.jobs.models import JobState
    from core.jobs.repository import JobRepository
    from core.memory import JsonFileMemory

    job_id = _submit(root)
    repo = JobRepository(JsonFileMemory(Path(root)))
    record = repo.get("acme", job_id)
    record.state = JobState.RUNNING
    repo.save(record)
    code, stdout, _ = _run(["jobs", "cancel", "--client", "acme", "--job-id", job_id, "--root", root])
    assert code == 4


def test_cancel_not_found_exits_3(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "jobs", "cancel", "--client", "acme", "--job-id", "nope", "--root", str(tmp_path / "mem"),
    ])
    assert code == 3


# ---------- missing required args ----------

def test_submit_missing_client_arg() -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["jobs", "submit", "--operation", "demo.echo"])
    assert exc.value.code == 2


def test_run_missing_job_id_arg() -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["jobs", "run", "--client", "acme"])
    assert exc.value.code == 2


# ---------- multi-tenant ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme", "--operation", "demo.echo",
        "--params", '{"message": "a"}', "--root", root,
    ])
    _run([
        "jobs", "submit", "--client", "other-client", "--operation", "demo.echo",
        "--params", '{"message": "b"}', "--root", root,
    ])
    code, stdout, _ = _run(["jobs", "list", "--client", "acme", "--root", root])
    assert json.loads(stdout)["count"] == 1


# ---------- audit ----------

def test_run_writes_audit(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root)
    _run(["jobs", "run", "--client", "acme", "--job-id", job_id, "--root", root])
    audit_root = Path(root) / "acme" / "audit"
    assert audit_root.exists()
    content = "\n".join(f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl"))
    assert '"job"' in content
    assert "completed" in content


# ---------- stdout/stderr contract ----------

def test_all_success_paths_emit_clean_json_on_stdout(tmp_path: Path) -> None:
    root = str(tmp_path / "mem")
    job_id = _submit(root)
    for argv in (
        ["jobs", "show", "--client", "acme", "--job-id", job_id, "--root", root],
        ["jobs", "list", "--client", "acme", "--root", root],
    ):
        code, stdout, _ = _run(argv)
        assert code == 0
        json.loads(stdout)  # raises if not clean JSON
