"""End-to-end mock dispatcher tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.contracts import EnvelopeStatus, WorkflowRunStatus
from core.memory import JsonFileMemory
from core.runtime import (
    ENVELOPE_KIND,
    WORKFLOW_RUN_KIND,
    MinimalDispatcher,
    MockAgent,
)
from core.workflows import WorkflowSpec, load_workflow

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


@pytest.fixture
def w1_spec() -> WorkflowSpec:
    return load_workflow(REPO_ROOT / "workflows" / "W1_intake_to_strategy.yaml")


# ---------- W1 happy path ----------

def test_run_w1_succeeds(mem: JsonFileMemory, w1_spec: WorkflowSpec) -> None:
    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    summary = dispatcher.run(w1_spec, client_slug="default")
    assert summary.status is WorkflowRunStatus.SUCCEEDED
    assert summary.client_slug == "default"
    assert summary.workflow_name == w1_spec.workflow_id


def test_run_w1_persists_envelopes(mem: JsonFileMemory, w1_spec: WorkflowSpec) -> None:
    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    summary = dispatcher.run(w1_spec, client_slug="default")
    envelopes = mem.list("default", ENVELOPE_KIND)
    assert len(envelopes) == len(summary.steps) == sum(
        len(p.agents) for p in w1_spec.phases
    )


def test_run_w1_persists_summary(mem: JsonFileMemory, w1_spec: WorkflowSpec) -> None:
    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    summary = dispatcher.run(w1_spec, client_slug="default")
    runs = mem.list("default", WORKFLOW_RUN_KIND)
    assert len(runs) == 1
    assert runs[0]["run_id"] == summary.run_id


def test_run_w1_emits_audit_events(mem: JsonFileMemory, w1_spec: WorkflowSpec) -> None:
    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    dispatcher.run(w1_spec, client_slug="default")
    events = mem.read_audit_events("default")
    # workflow_started + N envelope_received + workflow_finished
    event_types = [e.event_type.value for e in events]
    assert event_types[0] == "workflow_started"
    assert event_types[-1] == "workflow_finished"
    assert event_types.count("envelope_received") == sum(
        len(p.agents) for p in w1_spec.phases
    )


def test_run_w1_envelopes_pass_strict_validation(
    mem: JsonFileMemory, w1_spec: WorkflowSpec
) -> None:
    # The dispatcher already calls validate_envelope_strict; this asserts the
    # persisted payloads are themselves re-loadable via the contract.
    from core.contracts import validate_envelope_strict

    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    dispatcher.run(w1_spec, client_slug="default")
    for payload in mem.list("default", ENVELOPE_KIND):
        # Strip dispatcher metadata before re-validating.
        clean = {k: v for k, v in payload.items() if not k.startswith("__")}
        env = validate_envelope_strict(clean)
        assert env.status is EnvelopeStatus.COMPLETADO


def test_run_w1_audit_chain_is_valid(
    mem: JsonFileMemory, w1_spec: WorkflowSpec
) -> None:
    from core.contracts import verify_chain

    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    dispatcher.run(w1_spec, client_slug="default")
    events = mem.read_audit_events("default")
    assert verify_chain(events) == []


# ---------- gate enforcement ----------

def test_phase_fails_when_required_gate_missing(mem: JsonFileMemory) -> None:
    # Synthetic two-phase workflow where p2 requires a gate p1 does NOT emit.
    spec = WorkflowSpec.model_validate(
        {
            "workflow_id": "W9_synthetic",
            "version": 1,
            "spec_version": "workflow-spec.v1",
            "description": "x",
            "phases": [
                {
                    "id": "p1",
                    "agents": ["mock"],
                    "gates_required_before": [],
                    "gates_produced": [],
                },
                {
                    "id": "p2",
                    "agents": ["mock"],
                    "gates_required_before": ["g_missing_gate"],
                    "gates_produced": [],
                },
            ],
        }
    )
    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    summary = dispatcher.run(spec, client_slug="default")
    assert summary.status is WorkflowRunStatus.FAILED


# ---------- multi-tenant isolation ----------

def test_two_clients_have_independent_runs(
    mem: JsonFileMemory, w1_spec: WorkflowSpec
) -> None:
    dispatcher = MinimalDispatcher(memory=mem, agent=MockAgent())
    s1 = dispatcher.run(w1_spec, client_slug="demo-co")
    s2 = dispatcher.run(w1_spec, client_slug="acme")
    assert s1.run_id != s2.run_id
    assert mem.list("demo-co", WORKFLOW_RUN_KIND)[0]["run_id"] == s1.run_id
    assert mem.list("acme", WORKFLOW_RUN_KIND)[0]["run_id"] == s2.run_id
    # Cross-tenant must not leak.
    assert all(r["run_id"] != s2.run_id for r in mem.list("demo-co", WORKFLOW_RUN_KIND))


# ---------- MockAgent shape ----------

def test_mock_agent_produces_minimal_valid_envelope() -> None:
    from core.runtime.mock_agent import MockAgent, MockAgentInput

    env = MockAgent().run(
        MockAgentInput(
            agent_id="copywriter",
            phase_id="copy",
            workflow_id="W4_creative_factory_draft",
            client_slug="default",
        )
    )
    assert env.status is EnvelopeStatus.COMPLETADO
    assert env.agent == "copywriter"
    assert env.client_slug == "default"
    assert env.contract_version == "envelope.v1"
    assert env.artifacts and env.artifacts[0].path.startswith("mock://")
