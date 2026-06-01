"""Orchestrator-level tests for claude_invocations propagation (MKT-4B).

Uses a ScriptedClaudeInvoker that emits per-call records via the
``record_sink`` channel — same wire protocol as the SDK invoker, no
SDK dependency required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.contracts import verify_chain
from core.memory import JsonFileMemory
from core.pipeline import PipelineOrchestrator
from core.strategy import (
    ClaudeInvocationContext,
    ClaudeInvocationRecord,
    ClaudeInvoker,
    ClaudeInvokerError,
    ClaudeStrategyBackend,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


class _RecordingInvoker(ClaudeInvoker):
    """Always raises (so the backend falls back) but appends a record
    to the sink first — exactly the contract the SDK invoker honors."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, prompt: str, *, system, context: ClaudeInvocationContext) -> str:
        self.calls.append(context.method)
        if context.record_sink is not None:
            context.record_sink.append(
                ClaudeInvocationRecord(
                    method=context.method,
                    model="recording-mock",
                    request_id=f"req_{context.method}",
                    input_tokens=42,
                    output_tokens=21,
                    duration_ms=10.0,
                    ok=False,
                    error_type="RuntimeError",
                    error_message="forced fallback",
                )
            )
        raise ClaudeInvokerError("RuntimeError: forced fallback")


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path / "mem")


def test_invocation_records_land_in_summary(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    backend = ClaudeStrategyBackend(invoker=_RecordingInvoker())
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    assert len(summary.claude_invocations) == 6
    methods = {r.method for r in summary.claude_invocations}
    assert methods == {
        "value_proposition", "campaign_strategy", "creative_brief_pack",
        "social_post_drafts", "email_sequence", "reels_script_pack",
    }
    for r in summary.claude_invocations:
        assert r.ok is False
        assert r.request_id == f"req_{r.method}"
        assert r.error_type == "RuntimeError"


def test_invocation_events_in_audit_trail(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    backend = ClaudeStrategyBackend(invoker=_RecordingInvoker())
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    events = mem.read_audit_events(summary.client_slug)
    invocation_events = [
        e for e in events
        if e.payload.get("campaign_pipeline", {}).get("action")
        == "strategy_backend_invocation"
    ]
    assert len(invocation_events) == 6
    # Each event has the request_id + tokens.
    for ev in invocation_events:
        cp = ev.payload["campaign_pipeline"]
        assert cp["request_id"]
        assert cp["model"] == "recording-mock"
        assert cp["input_tokens"] == 42
        assert cp["output_tokens"] == 21
        assert cp["ok"] is False
        assert cp["error_type"] == "RuntimeError"


def test_audit_chain_valid_after_invocations(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    backend = ClaudeStrategyBackend(invoker=_RecordingInvoker())
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    events = mem.read_audit_events(summary.client_slug)
    assert verify_chain(events) == []


def test_renderer_includes_invocation_table(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    backend = ClaudeStrategyBackend(invoker=_RecordingInvoker())
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE, strategy_backend=backend)
    md_path = tmp_path / "out" / summary.client_slug / "campaign-final-summary.md"
    md = md_path.read_text(encoding="utf-8")
    assert "Invocaciones a Claude" in md
    assert "recording-mock" in md
    # Each method must appear in the table.
    for method in (
        "value_proposition", "campaign_strategy", "creative_brief_pack",
        "social_post_drafts", "email_sequence", "reels_script_pack",
    ):
        assert method in md


def test_templated_backend_produces_no_invocations(
    mem: JsonFileMemory, tmp_path: Path
) -> None:
    """Default path — no strategy_backend → empty claude_invocations."""
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(DEMO_INTAKE)
    assert summary.claude_invocations == []
