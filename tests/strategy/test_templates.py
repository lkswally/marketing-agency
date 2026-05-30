"""Determinism + structure tests for strategy template generators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy import StrategyInputBrief
from core.strategy.templates import (
    generate_approval_checklist,
    generate_buyer_persona,
    generate_campaign_strategy,
    generate_channel_recommendation,
    generate_competitor_benchmark,
    generate_creative_brief_pack,
    generate_diagnosis,
    generate_email_sequence,
    generate_executive_summary,
    generate_keyword_plan,
    generate_next_steps,
    generate_reels_script_pack,
    generate_risk_assessment,
    generate_schedule,
    generate_social_post_drafts,
    generate_suggested_pieces,
    generate_target_audience,
    generate_value_proposition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def brief() -> StrategyInputBrief:
    return StrategyInputBrief.model_validate(
        json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    )


# ---------- determinism ----------

def test_diagnosis_is_deterministic(brief: StrategyInputBrief) -> None:
    a = generate_diagnosis(brief)
    b = generate_diagnosis(brief)
    assert a.model_dump() == b.model_dump()


def test_keyword_plan_is_deterministic(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    a = generate_keyword_plan(brief, audience, vp)
    b = generate_keyword_plan(brief, audience, vp)
    assert a.model_dump() == b.model_dump()


def test_channel_recommendation_is_deterministic(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    a = generate_channel_recommendation(brief, audience)
    b = generate_channel_recommendation(brief, audience)
    # ChannelEntry rationale/labels are deterministic.
    assert [c.channel_type for c in a.channels] == [c.channel_type for c in b.channels]
    assert [c.priority for c in a.channels] == [c.priority for c in b.channels]


# ---------- structure ----------

def test_executive_summary_fields(brief: StrategyInputBrief) -> None:
    s = generate_executive_summary(brief)
    assert s.headline
    assert s.one_liner
    assert s.primary_objective == brief.objective
    assert len(s.one_liner) <= 280


def test_diagnosis_records_assumption_when_brand_voice_missing(brief: StrategyInputBrief) -> None:
    data = brief.model_dump()
    data["brand"]["tone_words"] = []
    no_voice_brief = StrategyInputBrief.model_validate(data)
    d = generate_diagnosis(no_voice_brief)
    assert any("Tono" in a for a in d.assumptions_made)


def test_target_audience_uses_first_hint(brief: StrategyInputBrief) -> None:
    a = generate_target_audience(brief)
    assert a.label == brief.audience_hints[0].label
    assert a.audience_id  # populated


def test_buyer_persona_has_motivations(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    persona = generate_buyer_persona(audience, brief)
    assert persona.motivations
    assert persona.objections
    assert persona.persona_id


def test_value_proposition_uses_brief_value_props(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    assert vp.differentiators
    # All declared value_props are surfaced.
    for p in brief.product.value_props:
        assert p in vp.differentiators


def test_competitor_benchmark_with_brief_competitors(brief: StrategyInputBrief) -> None:
    bench = generate_competitor_benchmark(brief.competitors_known)
    assert len(bench.competitors) == len(brief.competitors_known)
    assert bench.confidence in {"low", "medium", "high"}


def test_competitor_benchmark_with_no_competitors() -> None:
    bench = generate_competitor_benchmark([])
    assert bench.competitors == []
    assert bench.confidence == "low"


def test_channel_recommendation_caps_at_five(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    rec = generate_channel_recommendation(brief, audience)
    assert rec.total_channels <= 5
    assert len(rec.channels) == rec.total_channels
    # Priorities are 1..N consecutive.
    assert [c.priority for c in rec.channels] == list(range(1, len(rec.channels) + 1))


def test_channel_recommendation_includes_preferred_first(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    rec = generate_channel_recommendation(brief, audience)
    types = [c.channel_type for c in rec.channels]
    # Each preferred channel from brief or audience appears.
    seen_preferred = set(brief.preferred_channels) | set(brief.audience_hints[0].preferred_channels)
    for ch in seen_preferred:
        assert ch in types, f"preferred channel {ch} missing"


def test_keyword_plan_includes_clusters_and_negatives(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    kp = generate_keyword_plan(brief, audience, vp)
    assert kp.clusters
    assert kp.negative_keywords
    assert kp.hashtags
    # Competitor names appear as negatives.
    for c in brief.competitors_known:
        assert c.name.lower() in kp.negative_keywords


def test_campaign_strategy_uses_brief_objective(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    s = generate_campaign_strategy(brief, vp)
    assert s.objective == brief.objective
    assert s.duration_weeks == brief.duration_weeks
    assert s.primary_kpi == brief.primary_kpi


def test_creative_brief_pack_has_image_prompts(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    pack = generate_creative_brief_pack(brief, vp, audience)
    assert pack.briefs
    for b in pack.briefs:
        assert b.prompt_for_image_model
        assert b.aspect_ratio in {"1:1", "9:16", "16:9", "4:5"}


def test_social_drafts_use_recommended_channels(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    rec = generate_channel_recommendation(brief, audience)
    kp = generate_keyword_plan(brief, audience, vp)
    drafts = generate_social_post_drafts(brief, vp, rec, kp)
    assert drafts
    used_channels = {d.channel for d in drafts}
    rec_channels = {c.channel_type for c in rec.channels[:3]}
    assert used_channels.issubset(rec_channels)


def test_email_sequence_has_four_steps(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    seq = generate_email_sequence(brief, vp, audience)
    assert len(seq.emails) == 4
    assert [e.step for e in seq.emails] == [1, 2, 3, 4]


def test_reels_pack_has_three_scripts(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    pack = generate_reels_script_pack(brief, vp, audience)
    assert len(pack.scripts) == 3
    for s in pack.scripts:
        assert 10 <= s.target_duration_s <= 90


def test_schedule_has_entries_for_each_week(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    rec = generate_channel_recommendation(brief, audience)
    sched = generate_schedule(brief, rec)
    assert sched.weeks_total == brief.duration_weeks
    # At least one entry per week.
    weeks_with_entries = {e.week for e in sched.entries}
    assert weeks_with_entries == set(range(1, sched.weeks_total + 1))


def test_approval_checklist_has_blockers() -> None:
    ck = generate_approval_checklist()
    severities = {it.severity for it in ck.items}
    assert "blocker" in severities
    assert "must" in severities


def test_risk_assessment_flags_unverified_claims(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    vp = generate_value_proposition(brief, audience)
    bench = generate_competitor_benchmark(brief.competitors_known)
    risks = generate_risk_assessment(vp, bench)
    assert risks.unverified_claims_count >= 1
    assert risks.requires_compliance_audit is True


def test_next_steps_nonempty() -> None:
    assert generate_next_steps()


def test_suggested_pieces_match_channels(brief: StrategyInputBrief) -> None:
    audience = generate_target_audience(brief)
    rec = generate_channel_recommendation(brief, audience)
    pieces = generate_suggested_pieces(brief, rec)
    used = {p.channel for p in pieces}
    top4 = {c.channel_type for c in rec.channels[:4]}
    assert used == top4 or used.issubset(top4)
