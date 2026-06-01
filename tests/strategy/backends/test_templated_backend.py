"""TemplatedStrategyBackend produces valid Pydantic models, deterministically."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy import (
    BackendKind,
    CampaignStrategy,
    CreativeBriefPack,
    EmailSequenceDraft,
    ReelsScriptPack,
    SocialPostDraft,
    StrategyInputBrief,
    TargetAudience,
    TemplatedStrategyBackend,
    ValueProposition,
)
from core.strategy import templates as _t

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def brief() -> StrategyInputBrief:
    data = json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    return StrategyInputBrief.model_validate(data)


@pytest.fixture
def audience(brief: StrategyInputBrief) -> TargetAudience:
    return _t.generate_target_audience(brief)


@pytest.fixture
def backend() -> TemplatedStrategyBackend:
    return TemplatedStrategyBackend()


def test_kind_is_templated(backend: TemplatedStrategyBackend) -> None:
    assert backend.kind is BackendKind.TEMPLATED


def test_value_proposition_returns_valid_model(backend, brief, audience) -> None:
    vp = backend.value_proposition(brief, audience)
    assert isinstance(vp, ValueProposition)
    assert vp.headline


def test_campaign_strategy_returns_valid_model(backend, brief, audience) -> None:
    vp = backend.value_proposition(brief, audience)
    cs = backend.campaign_strategy(brief, vp)
    assert isinstance(cs, CampaignStrategy)
    assert 1 <= cs.duration_weeks <= 52


def test_creative_brief_pack_returns_valid_model(backend, brief, audience) -> None:
    vp = backend.value_proposition(brief, audience)
    pack = backend.creative_brief_pack(brief, vp, audience)
    assert isinstance(pack, CreativeBriefPack)


def test_social_post_drafts_returns_list_of_models(backend, brief, audience) -> None:
    vp = backend.value_proposition(brief, audience)
    channels = _t.generate_channel_recommendation(brief, audience)
    kw = _t.generate_keyword_plan(brief, audience, vp)
    drafts = backend.social_post_drafts(brief, vp, channels, kw)
    assert isinstance(drafts, list)
    assert all(isinstance(d, SocialPostDraft) for d in drafts)


def test_email_sequence_returns_valid_model(backend, brief, audience) -> None:
    vp = backend.value_proposition(brief, audience)
    seq = backend.email_sequence(brief, vp, audience)
    assert isinstance(seq, EmailSequenceDraft)


def test_reels_script_pack_returns_valid_model(backend, brief, audience) -> None:
    vp = backend.value_proposition(brief, audience)
    pack = backend.reels_script_pack(brief, vp, audience)
    assert isinstance(pack, ReelsScriptPack)


def test_templated_never_fallbacks(backend) -> None:
    # The templated backend has no fallback events to drain.
    assert backend.drain_fallback_events() == []


def test_two_runs_produce_identical_outputs(backend, brief, audience) -> None:
    a = backend.value_proposition(brief, audience)
    b = backend.value_proposition(brief, audience)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
