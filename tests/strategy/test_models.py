"""Pydantic validation tests for the strategy models."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.domain.enums import ChannelType
from core.strategy import (
    CAMPAIGN_STRATEGY_VERSION,
    ApprovalChecklist,
    BusinessDiagnosis,
    CampaignStrategy,
    CampaignStrategyReport,
    ChannelEntry,
    ChannelRecommendation,
    KeywordPlan,
    StrategyInputBrief,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


def _demo_brief_dict() -> dict:
    return json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))


# ---------- StrategyInputBrief ----------

def test_demo_brief_validates() -> None:
    brief = StrategyInputBrief.model_validate(_demo_brief_dict())
    assert brief.client.slug == "demo-saas"
    assert brief.duration_weeks == 8
    assert len(brief.audience_hints) == 1


def test_brief_requires_at_least_one_audience() -> None:
    data = _demo_brief_dict()
    data["audience_hints"] = []
    with pytest.raises(ValidationError):
        StrategyInputBrief.model_validate(data)


def test_brief_rejects_bad_client_slug() -> None:
    data = _demo_brief_dict()
    data["client"]["slug"] = "Bad Slug"
    with pytest.raises(ValidationError):
        StrategyInputBrief.model_validate(data)


def test_brief_rejects_negative_budget() -> None:
    data = _demo_brief_dict()
    data["budget_amount"] = -1
    with pytest.raises(ValidationError):
        StrategyInputBrief.model_validate(data)


def test_brief_duration_weeks_bounds() -> None:
    data = _demo_brief_dict()
    data["duration_weeks"] = 53
    with pytest.raises(ValidationError):
        StrategyInputBrief.model_validate(data)


def test_brief_round_trip_json() -> None:
    brief = StrategyInputBrief.model_validate(_demo_brief_dict())
    assert StrategyInputBrief.from_json(brief.to_json()).model_dump() == brief.model_dump()


# ---------- CampaignStrategyReport ----------

def _minimal_report() -> dict:
    return {
        "contract_version": CAMPAIGN_STRATEGY_VERSION,
        "report_id": "r1",
        "client_slug": "demo-co",
        "brief_id": "demo-co:current",
        "generated_at": datetime(2026, 5, 29, 12, 0, tzinfo=UTC).isoformat(),
        "executive_summary": {
            "headline": "h",
            "one_liner": "o",
            "primary_objective": "x",
            "key_metrics": [],
        },
        "diagnosis": {
            "stage_observed": "early traction",
        },
        "target_audience": {
            "audience_id": "a1",
            "label": "audience",
        },
        "value_proposition": {
            "headline": "vp",
            "category": "cat",
            "target_audience_label": "audience",
        },
        "competitor_benchmark": {},
        "channel_recommendation": {
            "channels": [],
            "total_channels": 0,
        },
        "keyword_plan": {},
        "campaign_strategy": {
            "objective": "x",
            "duration_weeks": 4,
            "primary_kpi": "leads",
        },
        "creative_brief_pack": {},
        "email_sequence": {
            "sequence_name": "s",
            "goal": "g",
            "audience_label": "a",
        },
        "reels_script_pack": {},
        "schedule": {
            "weeks_total": 4,
        },
        "approval_checklist": {},
        "risk_assessment": {},
    }


def test_minimal_report_validates() -> None:
    report = CampaignStrategyReport.model_validate(_minimal_report())
    assert report.contract_version == CAMPAIGN_STRATEGY_VERSION


def test_report_rejects_naive_timestamp() -> None:
    data = _minimal_report()
    data["generated_at"] = "2026-05-29T12:00:00"
    with pytest.raises(ValidationError):
        CampaignStrategyReport.model_validate(data)


def test_report_rejects_bad_slug() -> None:
    data = _minimal_report()
    data["client_slug"] = "Bad Slug"
    with pytest.raises(ValidationError):
        CampaignStrategyReport.model_validate(data)


def test_report_spec_version_pinned() -> None:
    data = _minimal_report()
    data["contract_version"] = "campaign-strategy.v2"
    with pytest.raises(ValidationError):
        CampaignStrategyReport.model_validate(data)


# ---------- Sub-models ----------

def test_channel_recommendation_priority_bounds() -> None:
    with pytest.raises(ValidationError):
        ChannelEntry(
            channel_type=ChannelType.NEWSLETTER,
            label="x",
            priority=99,
            rationale="x",
        )


def test_channel_recommendation_total_channels_capped() -> None:
    with pytest.raises(ValidationError):
        ChannelRecommendation(channels=[], total_channels=20)


def test_campaign_strategy_duration_bounds() -> None:
    with pytest.raises(ValidationError):
        CampaignStrategy(
            objective="x", duration_weeks=0, primary_kpi="leads"
        )


def test_diagnosis_default_fields() -> None:
    d = BusinessDiagnosis(stage_observed="x")
    assert d.industry is None
    assert d.strengths == []
    assert d.assumptions_made == []


def test_keyword_plan_defaults() -> None:
    kp = KeywordPlan()
    assert kp.source == "reasoning_only"
    assert kp.clusters == []
    assert kp.negative_keywords == []


def test_approval_checklist_default_empty() -> None:
    ck = ApprovalChecklist()
    assert ck.items == []
    assert ck.approvers_required == []


# ---------- Round-trip JSON ----------

def test_report_round_trip_json() -> None:
    report = CampaignStrategyReport.model_validate(_minimal_report())
    reloaded = CampaignStrategyReport.from_json(report.to_json())
    assert reloaded.model_dump() == report.model_dump()
