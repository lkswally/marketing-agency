"""ClaudeStrategyBackend fallback semantics.

Covers the three trigger paths:
1. Invoker raises (ClaudeInvokerError, including NoRealInvokerError).
2. Invoker returns malformed JSON.
3. Invoker returns JSON that fails Pydantic validation.

In all three cases the output MUST equal the templated backend output
and a BackendFallbackEvent MUST be recorded with the right method,
backends and reason.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy import (
    BackendKind,
    ClaudeStrategyBackend,
    RefusingClaudeInvoker,
    ScriptedClaudeInvoker,
    StrategyInputBrief,
    TargetAudience,
    TemplatedStrategyBackend,
    ValueProposition,
)
from core.strategy import templates as _t
from core.strategy.backends.invoker import ClaudeInvocationContext, ClaudeInvoker

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def brief() -> StrategyInputBrief:
    data = json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    return StrategyInputBrief.model_validate(data)


@pytest.fixture
def audience(brief) -> TargetAudience:
    return _t.generate_target_audience(brief)


@pytest.fixture
def templated() -> TemplatedStrategyBackend:
    return TemplatedStrategyBackend()


# ---------- 1. Invoker raises ----------


def test_refusing_invoker_falls_back(brief, audience, templated) -> None:
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    vp_claude = backend.value_proposition(brief, audience)
    vp_template = templated.value_proposition(brief, audience)
    assert vp_claude.model_dump(mode="json") == vp_template.model_dump(mode="json")

    events = backend.drain_fallback_events()
    assert len(events) == 1
    ev = events[0]
    assert ev.method == "value_proposition"
    assert ev.requested_backend is BackendKind.CLAUDE
    assert ev.fallback_backend is BackendKind.TEMPLATED
    assert "NoRealInvokerError" in ev.reason


def test_invoker_raising_generic_error_falls_back(brief, audience, templated) -> None:
    inv = ScriptedClaudeInvoker(responses={})  # no method registered → raises
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = backend.value_proposition(brief, audience)
    assert vp.model_dump(mode="json") == templated.value_proposition(
        brief, audience
    ).model_dump(mode="json")
    events = backend.drain_fallback_events()
    assert len(events) == 1
    assert "ClaudeInvokerError" in events[0].reason


# ---------- 2. Malformed JSON ----------


def test_malformed_json_falls_back(brief, audience, templated) -> None:
    inv = ScriptedClaudeInvoker(
        responses={"value_proposition": "this is not JSON {{{"}
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = backend.value_proposition(brief, audience)
    assert isinstance(vp, ValueProposition)
    assert vp.model_dump(mode="json") == templated.value_proposition(
        brief, audience
    ).model_dump(mode="json")
    events = backend.drain_fallback_events()
    assert len(events) == 1
    assert "ClaudeOutputInvalid" in events[0].reason


# ---------- 3. Pydantic validation error ----------


def test_invalid_pydantic_payload_falls_back(brief, audience, templated) -> None:
    inv = ScriptedClaudeInvoker(
        responses={
            "value_proposition": json.dumps(
                {
                    # Missing required fields, headline too short, etc.
                    "headline": "",  # min_length=1 violation
                    "category": "x",
                    "target_audience_label": "y",
                }
            )
        }
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = backend.value_proposition(brief, audience)
    assert vp.model_dump(mode="json") == templated.value_proposition(
        brief, audience
    ).model_dump(mode="json")
    events = backend.drain_fallback_events()
    assert len(events) == 1
    assert "ValidationError" in events[0].reason


# ---------- social_post_drafts wrapper specifics ----------


def test_social_drafts_missing_items_key_falls_back(brief, audience, templated) -> None:
    inv = ScriptedClaudeInvoker(
        responses={"social_post_drafts": json.dumps({"wrong": []})}
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = _t.generate_value_proposition(brief, audience)
    channels = _t.generate_channel_recommendation(brief, audience)
    kw = _t.generate_keyword_plan(brief, audience, vp)
    drafts = backend.social_post_drafts(brief, vp, channels, kw)
    expected = templated.social_post_drafts(brief, vp, channels, kw)
    # Same shape — same length and same channel ordering. post_id is a fresh
    # random id per call (new_id()), so we compare structurally not byte-wise.
    assert len(drafts) == len(expected) and len(drafts) > 0
    assert [d.channel for d in drafts] == [d.channel for d in expected]
    events = backend.drain_fallback_events()
    assert len(events) == 1
    assert events[0].method == "social_post_drafts"


def test_social_drafts_items_not_list_falls_back(brief, audience, templated) -> None:
    inv = ScriptedClaudeInvoker(
        responses={"social_post_drafts": json.dumps({"items": "not-a-list"})}
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = _t.generate_value_proposition(brief, audience)
    channels = _t.generate_channel_recommendation(brief, audience)
    kw = _t.generate_keyword_plan(brief, audience, vp)
    drafts = backend.social_post_drafts(brief, vp, channels, kw)
    assert len(drafts) == len(templated.social_post_drafts(brief, vp, channels, kw))
    events = backend.drain_fallback_events()
    assert len(events) == 1


# ---------- safety: oversized output ----------


class _OversizedInvoker(ClaudeInvoker):
    def complete(self, prompt, *, system, context):
        # 300 KB > 256 KB ceiling.
        return "x" * (300 * 1024)


def test_oversized_invoker_output_falls_back(brief, audience, templated) -> None:
    backend = ClaudeStrategyBackend(invoker=_OversizedInvoker())
    vp = backend.value_proposition(brief, audience)
    assert vp.model_dump(mode="json") == templated.value_proposition(
        brief, audience
    ).model_dump(mode="json")
    events = backend.drain_fallback_events()
    assert len(events) == 1
    assert "ClaudeOutputInvalid" in events[0].reason


class _NonStringInvoker(ClaudeInvoker):
    def complete(self, prompt, *, system, context):
        return 12345  # type: ignore[return-value]


def test_non_string_invoker_output_falls_back(brief, audience, templated) -> None:
    backend = ClaudeStrategyBackend(invoker=_NonStringInvoker())
    vp = backend.value_proposition(brief, audience)
    assert vp.model_dump(mode="json") == templated.value_proposition(
        brief, audience
    ).model_dump(mode="json")
    events = backend.drain_fallback_events()
    assert len(events) == 1


# ---------- drain semantics ----------


def test_drain_clears_events(brief, audience) -> None:
    backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
    backend.value_proposition(brief, audience)
    assert len(backend.drain_fallback_events()) == 1
    assert backend.drain_fallback_events() == []


# ---------- invoker context plumbing ----------


def test_set_client_slug_propagates_to_invoker() -> None:
    """The slug the backend receives must be the one the invoker sees."""

    captured: list[ClaudeInvocationContext] = []

    class _CapturingInvoker(ClaudeInvoker):
        def complete(self, prompt, *, system, context):
            captured.append(context)
            return "{}"  # invalid for ValueProp but we only care about the ctx

    backend = ClaudeStrategyBackend(invoker=_CapturingInvoker())
    backend.set_client_slug("acme-bootstrapped")
    # Trigger any call.
    brief_data = json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    b = StrategyInputBrief.model_validate(brief_data)
    a = _t.generate_target_audience(b)
    backend.value_proposition(b, a)

    assert len(captured) == 1
    assert captured[0].client_slug == "acme-bootstrapped"
    assert captured[0].method == "value_proposition"
