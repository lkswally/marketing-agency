"""Tests for the campaign.run job operation (MKT-11D).

Covers registry registration, cancel/artifact/approval metadata, the
handler's outcome translation, and double-execution / idempotency
protection specifically for this operation.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.application.context import OperationContext
from core.jobs import InlineJobRunner, JobRegistry, JobRiskClass, JobState
from core.jobs.operations.campaign import register_campaign_operations
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _registry() -> JobRegistry:
    reg = JobRegistry()
    register_campaign_operations(reg)
    return reg


def _risky_intake(tmp_path: Path) -> Path:
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    path = tmp_path / "risky.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------- registration ----------

def test_campaign_run_is_registered() -> None:
    reg = _registry()
    assert reg.is_registered("campaign.run")


def test_campaign_run_spec_metadata() -> None:
    reg = _registry()
    spec = reg.resolve("campaign.run")
    assert spec.risk_class is JobRiskClass.HIGH
    assert spec.cancel_support is False
    assert spec.long_running is True
    assert spec.produces_artifacts is True
    assert spec.may_wait_for_approval is True
    assert spec.dev_only is False


def test_default_registry_has_campaign_run_after_importing_services() -> None:
    """Documents the real import-order constraint found while building
    this operation (see core/jobs/__init__.py) — campaign.run is only
    guaranteed on default_registry once core.application.services.jobs
    has been imported. Every production path (the CLI) already does
    this."""
    from core.application.services import jobs as _  # noqa: F401
    from core.jobs import default_registry

    assert default_registry.is_registered("campaign.run")


# ---------- handler via InlineJobRunner ----------

def test_campaign_run_completed(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    reg = _registry()
    runner = InlineJobRunner(memory, root=tmp_path / "mem", registry=reg)
    ctx = OperationContext(
        client_slug="acme-bootstrapped", root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )
    record = runner.submit(
        ctx, operation="campaign.run", params={"intake_path": str(DEMO_INTAKE)},
    )
    result = runner.run(record.client_slug, record.job_id)
    assert result.state is JobState.COMPLETED
    assert result.result_data is not None
    assert result.result_data["client_slug"] == "acme-bootstrapped"
    assert result.result_ref == "acme-bootstrapped/campaign_run_summary/current"


def test_campaign_run_waiting_approval_carries_partial_data(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    reg = _registry()
    runner = InlineJobRunner(memory, root=tmp_path / "mem", registry=reg)
    risky = _risky_intake(tmp_path)
    ctx = OperationContext(
        client_slug="acme-bootstrapped", root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )
    record = runner.submit(
        ctx, operation="campaign.run",
        params={"intake_path": str(risky), "require_approval": True},
    )
    result = runner.run(record.client_slug, record.job_id)
    assert result.state is JobState.WAITING_APPROVAL
    assert result.approval_reason is not None
    # Adjustment 4: artifacts already produced must not be lost.
    assert result.result_data is not None
    assert result.result_data["blocks_publish"] is True
    assert result.result_data["approval_pack_id"]
    assert result.result_ref == "acme-bootstrapped/approval_pack/current"


def test_campaign_run_failed_missing_intake(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    reg = _registry()
    runner = InlineJobRunner(memory, root=tmp_path / "mem", registry=reg)
    ctx = OperationContext(
        client_slug="acme-bootstrapped", root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )
    record = runner.submit(
        ctx, operation="campaign.run",
        params={"intake_path": str(tmp_path / "nope.json")},
    )
    result = runner.run(record.client_slug, record.job_id)
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "not found" in result.error.message


# ---------- double execution / idempotency ----------

def test_double_run_is_idempotent_no_reexecution(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    reg = _registry()
    runner = InlineJobRunner(memory, root=tmp_path / "mem", registry=reg)
    ctx = OperationContext(
        client_slug="acme-bootstrapped", root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )
    record = runner.submit(
        ctx, operation="campaign.run", params={"intake_path": str(DEMO_INTAKE)},
    )
    first = runner.run(record.client_slug, record.job_id)
    second = runner.run(record.client_slug, record.job_id)
    assert first.state is JobState.COMPLETED
    assert second.state is JobState.COMPLETED
    # Same summary run_id both times — pipeline was not re-executed.
    assert first.result_data["run_id"] == second.result_data["run_id"]


def test_multi_tenant_isolation(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    reg = _registry()
    runner = InlineJobRunner(memory, root=tmp_path / "mem", registry=reg)
    ctx_acme = OperationContext(
        client_slug="acme-bootstrapped", root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )
    record = runner.submit(
        ctx_acme, operation="campaign.run", params={"intake_path": str(DEMO_INTAKE)},
    )
    result = runner.run(record.client_slug, record.job_id)
    assert result.client_slug == "acme-bootstrapped"
    # A second client's job list must not see this job.
    from core.jobs.repository import JobRepository

    repo = JobRepository(memory)
    assert repo.list_for_client("other-client") == []
    assert len(repo.list_for_client("acme-bootstrapped")) == 1
