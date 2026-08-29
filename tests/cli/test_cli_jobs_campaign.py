"""CLI tests for ``mkt jobs submit --operation campaign.run`` (MKT-11D).

Covers: the job-facing path end to end via the CLI adapter, clean stdout
JSON, exit code 7 on job FAILED, secret non-leakage into stdout/stderr,
and that the legacy ``mkt run-campaign`` command's own exit codes (0/2/3/4)
are untouched — those live in ``tests/cli/test_cli_run_campaign.py`` as
regression pins and are not duplicated here.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


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


def _risky_intake(tmp_path: Path) -> Path:
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    path = tmp_path / "risky.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------- submit --run: COMPLETED ----------

def test_submit_run_campaign_completed(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["state"] == "completed"
    assert payload["result_data"]["client_slug"] == "acme-bootstrapped"


def test_submit_run_writes_expected_artifacts(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    assert code == 0
    payload = json.loads(stdout)
    client_out = Path(payload["result_data"]["outputs_dir"])
    assert (client_out / "campaign-final-summary.json").exists()
    assert (client_out / "approval-pack.json").exists()


# ---------- submit --run: WAITING_APPROVAL ----------

def test_submit_run_campaign_waiting_approval(tmp_path: Path) -> None:
    risky = _risky_intake(tmp_path)
    params = json.dumps({"intake_path": str(risky), "require_approval": True})
    code, stdout, _ = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    assert code == 0, stdout  # WAITING_APPROVAL is an operational success, not exit 7
    payload = json.loads(stdout)
    assert payload["state"] == "waiting_approval"
    assert payload["approval_reason"]
    assert payload["result_data"]["blocks_publish"] is True


# ---------- submit --run: FAILED ----------

def test_submit_run_campaign_failed_missing_intake(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(tmp_path / "nope.json")})
    code, stdout, stderr = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    assert code == 7  # ExitCode.JOB_FAILED — distinct from legacy run-campaign's exit 2
    assert "job failed" in stderr.lower()
    payload = json.loads(stdout)  # stdout stays clean JSON even on failure
    assert payload["state"] == "failed"
    assert payload["error"]["code"] == "invalid_input"


# ---------- two-step submit then run ----------

def test_submit_then_separate_run(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    code1, stdout1, _ = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code1 == 0
    job_id = json.loads(stdout1)["job_id"]

    code2, stdout2, _ = _run([
        "jobs", "run", "--client", "acme-bootstrapped", "--job-id", job_id,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code2 == 0
    assert json.loads(stdout2)["state"] == "completed"


def test_show_after_run_reflects_state(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    _, stdout1, _ = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    job_id = json.loads(stdout1)["job_id"]
    code, stdout, _ = _run([
        "jobs", "show", "--client", "acme-bootstrapped", "--job-id", job_id,
        "--root", str(tmp_path / "mem"),
    ])
    assert code == 0
    assert json.loads(stdout)["state"] == "completed"


# ---------- secret leakage ----------

def test_no_secret_in_stdout_or_stderr(tmp_path: Path, monkeypatch) -> None:
    """Deliberately does NOT set ANTHROPIC_API_KEY: doing so would make
    resolve_strategy_backend() construct a real anthropic.Anthropic(...)
    client, importing the optional SDK for real and permanently polluting
    sys.modules for the rest of the pytest session — breaking this
    project's existing "no SDK ever imported by default" isolation pins
    elsewhere in the suite (found via a full-suite run, not assumed; see
    docs/MKT-11D-Campaign-Job-Migration-Inventory.md). The no-key path
    (RefusingClaudeInvoker + a WARNING string) is what would leak a
    secret if anything did — that's the path this test actually
    exercises with a secret-shaped env var."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SOME_OTHER_SECRET_LOOKALIKE", "sk-should-never-appear-anywhere")
    params = json.dumps({"intake_path": str(DEMO_INTAKE), "backend": "claude"})
    code, stdout, stderr = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    assert "sk-should-never-appear-anywhere" not in stdout
    assert "sk-should-never-appear-anywhere" not in stderr


def test_no_secret_in_persisted_job_record(tmp_path: Path, monkeypatch) -> None:
    """See test_no_secret_in_stdout_or_stderr for why ANTHROPIC_API_KEY
    is deliberately left unset here."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SOME_OTHER_SECRET_LOOKALIKE", "sk-should-never-be-persisted")
    params = json.dumps({"intake_path": str(DEMO_INTAKE), "backend": "claude"})
    _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    from core.jobs.repository import JobRepository
    from core.memory import JsonFileMemory

    repo = JobRepository(JsonFileMemory(tmp_path / "mem"))
    jobs = repo.list_for_client("acme-bootstrapped")
    assert len(jobs) == 1
    raw = jobs[0].model_dump_json()
    assert "sk-should-never-be-persisted" not in raw


# ---------- list / filter ----------

def test_list_filters_campaign_jobs_by_operation(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"), "--run",
    ])
    _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "demo.echo", "--params", json.dumps({"message": "hi"}),
        "--root", str(tmp_path / "mem"), "--run",
    ])
    code, stdout, _ = _run([
        "jobs", "list", "--client", "acme-bootstrapped",
        "--root", str(tmp_path / "mem"), "--operation", "campaign.run",
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 1
    assert payload["jobs"][0]["operation"] == "campaign.run"


# ---------- audit trail ----------

def test_job_run_writes_audit_correlated_with_pipeline(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    _, stdout, _ = _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    job_id = json.loads(stdout)["job_id"]

    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme-bootstrapped")
    job_events = [e.payload["job"] for e in events if "job" in e.payload]
    pipeline_events = [
        e.payload["campaign_pipeline"] for e in events if "campaign_pipeline" in e.payload
    ]
    assert any(je["job_id"] == job_id for je in job_events)
    assert any(pe.get("job_id") == job_id for pe in pipeline_events)


# ---------- multi-tenant isolation ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    params = json.dumps({"intake_path": str(DEMO_INTAKE)})
    _run([
        "jobs", "submit", "--client", "acme-bootstrapped",
        "--operation", "campaign.run", "--params", params,
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
        "--run",
    ])
    code, stdout, _ = _run([
        "jobs", "list", "--client", "other-client", "--root", str(tmp_path / "mem"),
    ])
    assert code == 0
    assert json.loads(stdout)["count"] == 0


# ---------- legacy CLI still works (spot check, full pins in test_cli_run_campaign.py) ----------

def test_legacy_run_campaign_still_works_unmigrated(tmp_path: Path) -> None:
    code, stdout, _ = _run([
        "run-campaign", "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"), "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["client_slug"] == "acme-bootstrapped"
