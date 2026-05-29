"""Backend interface tests — MockAgentBackend conforms, ClaudeCodeBackend raises."""

from __future__ import annotations

import pytest

from core.contracts import EnvelopeStatus, ReturnEnvelope
from core.runtime import (
    AgentBackend,
    AgentInvocation,
    ClaudeCodeBackend,
    MockAgentBackend,
)


def _inv(**overrides) -> AgentInvocation:
    base = dict(
        agent_id="copywriter",
        phase_id="copy",
        workflow_id="W4_creative_factory_draft",
        client_slug="default",
    )
    base.update(overrides)
    return AgentInvocation(**base)


# ---------- MockAgentBackend ----------

def test_mock_is_an_agent_backend() -> None:
    assert isinstance(MockAgentBackend(), AgentBackend)


def test_mock_produces_envelope() -> None:
    env = MockAgentBackend().run(_inv())
    assert isinstance(env, ReturnEnvelope)
    assert env.status is EnvelopeStatus.COMPLETADO
    assert env.agent == "copywriter"
    assert env.client_slug == "default"


def test_mock_is_deterministic_for_fixed_invocation() -> None:
    # Same agent_id / phase / workflow / client → identical artifact path.
    a = MockAgentBackend().run(_inv())
    b = MockAgentBackend().run(_inv())
    assert a.artifacts[0].path == b.artifacts[0].path


def test_mock_artifact_path_includes_agent_and_phase() -> None:
    env = MockAgentBackend().run(_inv())
    assert env.artifacts[0].path.startswith("mock://copywriter/copy")


# ---------- ClaudeCodeBackend ----------

def test_claude_code_is_an_agent_backend() -> None:
    assert isinstance(ClaudeCodeBackend(), AgentBackend)


def test_claude_code_constructor_accepts_kwargs() -> None:
    # Future implementations may take config; today we accept silently.
    backend = ClaudeCodeBackend(model="opus", timeout_s=120)
    assert isinstance(backend, AgentBackend)


def test_claude_code_run_raises_not_implemented() -> None:
    backend = ClaudeCodeBackend()
    with pytest.raises(NotImplementedError) as exc:
        backend.run(_inv())
    msg = str(exc.value)
    assert "scaffolding" in msg.lower()
    assert "safety" in msg.lower() or "agent-backend-safety" in msg


def test_claude_code_does_not_import_anthropic_sdk() -> None:
    # Smoke check: importing the backend must not pull in any SDK.
    import sys

    import core.runtime.backends.claude_code as cc

    assert "anthropic" not in sys.modules or sys.modules["anthropic"] is None
    # Confirm the module's own globals carry no SDK reference.
    assert "anthropic" not in dir(cc)


# ---------- AgentInvocation ----------

def test_invocation_is_frozen() -> None:
    import dataclasses

    inv = _inv()
    with pytest.raises(dataclasses.FrozenInstanceError):
        inv.agent_id = "other"  # type: ignore[misc]


def test_invocation_field_access() -> None:
    inv = _inv()
    assert inv.agent_id == "copywriter"
    assert inv.phase_id == "copy"
    assert inv.workflow_id == "W4_creative_factory_draft"
    assert inv.client_slug == "default"
