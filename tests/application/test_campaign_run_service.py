"""Tests for the campaign run application service (MKT-11D).

Covers: params validation, backend selection (templated/Claude/fallback),
secret non-persistence, the three CampaignRunOutcome kinds (COMPLETED /
BLOCKED / STRICT_FAILURE), execution-time intake re-validation
(Adjustment 2), and audit correlation (Adjustment 3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.application.services.campaign_run import (
    CampaignRunOutcomeKind,
    CampaignRunParams,
    resolve_strategy_backend,
    run_campaign,
)
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _risky_intake(tmp_path: Path) -> Path:
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    path = tmp_path / "risky.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------- CampaignRunParams ----------

def test_params_valid_minimal() -> None:
    p = CampaignRunParams(intake_path="x.json")
    assert p.strict is False
    assert p.require_approval is False
    assert p.stop_on_blocked is False
    assert p.backend == "templated"
    assert p.claude_model is None


def test_params_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        CampaignRunParams(intake_path="x.json", client="not-a-real-param")


def test_params_rejects_invalid_backend() -> None:
    with pytest.raises(ValidationError):
        CampaignRunParams(intake_path="x.json", backend="gpt4")


def test_params_no_client_field_exists() -> None:
    """MKT-11D explicitly does not invent a --client param — client_slug
    comes from the intake file, exactly like the legacy CLI."""
    assert "client_slug" not in CampaignRunParams.model_fields
    assert "client" not in CampaignRunParams.model_fields


# ---------- resolve_strategy_backend ----------

def test_resolve_backend_templated_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, warning = resolve_strategy_backend("templated", None)
    assert backend is None
    assert warning is None


def test_resolve_backend_claude_no_key_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    backend, warning = resolve_strategy_backend("claude", None)
    assert backend is not None
    assert warning is not None
    assert "ANTHROPIC_API_KEY" in warning


def test_resolve_backend_secret_never_in_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The only branch that emits a warning is the no-key / no-SDK path
    (core/application/services/campaign_run.py::resolve_strategy_backend)
    — when a key IS present, the function returns warning=None
    unconditionally (no SDK error text to leak from). This test therefore
    deliberately does NOT set ANTHROPIC_API_KEY: doing so would force a
    real ``anthropic.Anthropic(...)`` client construction and import the
    optional SDK for real, which would permanently pollute ``sys.modules``
    for the rest of the pytest session and break the project's existing
    "no SDK ever imported by default" isolation pins
    (tests/runtime/test_backend_interface.py,
    tests/notion_sync/test_planner.py) — found the hard way, via a full
    suite run, not assumed."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SOME_OTHER_SECRET_LOOKALIKE", "sk-should-not-leak-either")
    _backend, warning = resolve_strategy_backend("templated", None)
    assert warning is None  # templated path never even looks at the key
    _backend2, warning2 = resolve_strategy_backend("claude", None)
    assert warning2 is not None
    assert "sk-should-not-leak-either" not in warning2


# ---------- run_campaign: COMPLETED ----------

def test_run_campaign_completed(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    params = CampaignRunParams(intake_path=str(DEMO_INTAKE))
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.COMPLETED
    assert outcome.summary_data is not None
    assert outcome.summary_data["client_slug"] == "acme-bootstrapped"
    assert outcome.summary_data["blocks_publish"] is False


def test_run_campaign_completed_no_secret_in_data(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    params = CampaignRunParams(intake_path=str(DEMO_INTAKE))
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    raw = json.dumps(outcome.model_dump(mode="json"))
    assert "ANTHROPIC_API_KEY" not in raw
    assert "sk-" not in raw


# ---------- run_campaign: BLOCKED ----------

def test_run_campaign_blocked_via_require_approval(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    risky = _risky_intake(tmp_path)
    params = CampaignRunParams(intake_path=str(risky), require_approval=True)
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.BLOCKED
    assert outcome.summary_data["blocks_publish"] is True


def test_run_campaign_blocked_via_stop_on_blocked(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    risky = _risky_intake(tmp_path)
    params = CampaignRunParams(intake_path=str(risky), stop_on_blocked=True)
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.BLOCKED
    assert outcome.summary_data["blocks_publish"] is True


def test_run_campaign_blocked_via_default_flags(tmp_path: Path) -> None:
    """Neither --require-approval nor --stop-on-blocked: the legacy CLI
    would exit 0 here (quiet return), but the job-facing outcome is still
    BLOCKED — the approved MKT-11D design point."""
    memory = JsonFileMemory(tmp_path / "mem")
    risky = _risky_intake(tmp_path)
    params = CampaignRunParams(intake_path=str(risky))
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.BLOCKED


def test_run_campaign_blocked_all_three_flag_combos_agree(tmp_path: Path) -> None:
    """The three flag combinations that can reach a blocked pipeline all
    produce the same job-facing outcome kind — confirms the mapping keys
    off blocks_publish, not off which flag triggered it."""
    kinds = set()
    for flags in (
        {"require_approval": True},
        {"stop_on_blocked": True},
        {},
    ):
        memory = JsonFileMemory(tmp_path / f"mem-{len(kinds)}")
        risky = _risky_intake(tmp_path)
        params = CampaignRunParams(intake_path=str(risky), **flags)
        outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
        kinds.add(outcome.kind)
    assert kinds == {CampaignRunOutcomeKind.BLOCKED}


# ---------- run_campaign: STRICT_FAILURE ----------

def test_run_campaign_missing_intake_is_strict_failure(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    params = CampaignRunParams(intake_path=str(tmp_path / "nope.json"))
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.STRICT_FAILURE
    assert "not found" in outcome.message


def test_run_campaign_malformed_intake_is_strict_failure(tmp_path: Path) -> None:
    """Adjustment 2: the service (used by the job path) never trusts an
    earlier preflight — a corrupted/unparseable intake fails for real,
    unlike the legacy CLI's graceful degradation."""
    memory = JsonFileMemory(tmp_path / "mem")
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    params = CampaignRunParams(intake_path=str(bad))
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.STRICT_FAILURE


def test_run_campaign_strict_critical_is_strict_failure(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )
    params = CampaignRunParams(intake_path=str(bad), strict=True)
    outcome = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome.kind is CampaignRunOutcomeKind.STRICT_FAILURE
    assert "strict" in outcome.message.lower() or "critical" in outcome.message.lower()


# ---------- Adjustment 3: audit correlation ----------

def test_job_id_propagates_into_pipeline_audit(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    params = CampaignRunParams(intake_path=str(DEMO_INTAKE))
    run_campaign(
        memory=memory, outputs_root=tmp_path / "out", params=params,
        job_id="job-abc-123", correlation_id="corr-xyz-789",
    )
    events = memory.read_audit_events("acme-bootstrapped")
    pipeline_events = [
        e.payload["campaign_pipeline"] for e in events if "campaign_pipeline" in e.payload
    ]
    assert pipeline_events  # at least one
    assert any(p.get("job_id") == "job-abc-123" for p in pipeline_events)
    assert any(p.get("correlation_id") == "corr-xyz-789" for p in pipeline_events)


def test_no_job_id_means_no_job_id_key_in_audit(tmp_path: Path) -> None:
    """Legacy (non-job) calls must not gain new payload keys — byte-shape
    compatibility for anything inspecting the audit payload."""
    memory = JsonFileMemory(tmp_path / "mem")
    params = CampaignRunParams(intake_path=str(DEMO_INTAKE))
    run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    events = memory.read_audit_events("acme-bootstrapped")
    pipeline_events = [
        e.payload["campaign_pipeline"] for e in events if "campaign_pipeline" in e.payload
    ]
    assert all("job_id" not in p for p in pipeline_events)
    assert all("correlation_id" not in p for p in pipeline_events)


# ---------- Multi-tenant isolation ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    memory = JsonFileMemory(tmp_path / "mem")
    params = CampaignRunParams(intake_path=str(DEMO_INTAKE))
    outcome1 = run_campaign(memory=memory, outputs_root=tmp_path / "out", params=params)
    assert outcome1.summary_data["client_slug"] == "acme-bootstrapped"
    # No cross-tenant leakage possible here since client_slug is derived
    # from the intake file itself — pinned so a future refactor can't
    # accidentally add a way to override it independently of the intake.
