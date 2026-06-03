"""Pydantic validation tests for the next-campaign iteration models."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from core.iteration import (
    NEXT_CAMPAIGN_ITERATION_PLAN_VERSION,
    ABTestHypothesis,
    IterationAction,
    IterationActionKind,
    IterationActionPriority,
    IterationCalendarEntry,
    IterationExecutiveSummary,
    IterationStats,
    NewContentIdea,
    NewContentKind,
    NextCampaignIterationPlan,
)
from core.iteration.models import SuggestedIterationTask


def _now() -> datetime:
    return datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _stats(**overrides) -> IterationStats:
    base = dict(
        total_actions=0, repeats=0, pauses=0, improves=0, creates=0,
        channel_adjustments=0, new_content_ideas=0,
        ab_test_hypotheses=0, calendar_entries=0, suggested_tasks=0,
    )
    base.update(overrides)
    return IterationStats(**base)


def _plan(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "feedback_pack_id": "fb1",
        "feedback_pack_contract_version": "campaign-feedback-pack.v1",
        "stats": _stats().model_dump(mode="json"),
        "created_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


# ---------- IterationAction ----------

def test_action_minimal() -> None:
    a = IterationAction(
        kind=IterationActionKind.REPEAT_PIECE,
        priority=IterationActionPriority.HIGH,
        title="repeat post-001",
        rationale="r",
        suggested_next_step="do x",
    )
    assert a.kind is IterationActionKind.REPEAT_PIECE


def test_action_all_kinds_validate() -> None:
    for k in IterationActionKind:
        IterationAction(
            kind=k, priority=IterationActionPriority.MEDIUM,
            title="t", rationale="r", suggested_next_step="s",
        )


# ---------- NewContentIdea ----------

def test_new_content_idea_all_kinds() -> None:
    for k in NewContentKind:
        NewContentIdea(kind=k, title="t", rationale="r")


# ---------- ABTestHypothesis ----------

def test_ab_test_minimal() -> None:
    h = ABTestHypothesis(
        surface="email_subject",
        variant_a="A", variant_b="B",
        success_metric="open_rate",
        success_threshold="uplift >= 20%",
        rationale="r",
    )
    assert h.surface == "email_subject"


def test_ab_test_oversize_variant_rejected() -> None:
    with pytest.raises(ValidationError):
        ABTestHypothesis(
            surface="x", variant_a="x" * 500, variant_b="B",
            success_metric="m", success_threshold="t", rationale="r",
        )


# ---------- IterationCalendarEntry ----------

def test_calendar_entry_minimal() -> None:
    e = IterationCalendarEntry(week=1, channel="newsletter", piece_type="email")
    assert e.week == 1
    assert e.suggested_date is None


def test_calendar_entry_with_date() -> None:
    e = IterationCalendarEntry(
        week=2, suggested_date=date(2026, 7, 1),
        channel="blog", piece_type="article",
    )
    assert e.suggested_date == date(2026, 7, 1)


def test_calendar_entry_invalid_week() -> None:
    with pytest.raises(ValidationError):
        IterationCalendarEntry(week=0, channel="x", piece_type="y")
    with pytest.raises(ValidationError):
        IterationCalendarEntry(week=53, channel="x", piece_type="y")


# ---------- NextCampaignIterationPlan ----------

def test_minimal_plan_validates() -> None:
    p = NextCampaignIterationPlan.model_validate(_plan())
    assert p.contract_version == NEXT_CAMPAIGN_ITERATION_PLAN_VERSION
    assert p.total_items == 0


def test_plan_round_trip() -> None:
    p = NextCampaignIterationPlan.model_validate(_plan())
    reloaded = NextCampaignIterationPlan.from_json(p.to_json())
    assert reloaded.model_dump() == p.model_dump()


def test_plan_naive_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        NextCampaignIterationPlan.model_validate(_plan(created_at="2026-06-02T12:00:00"))


def test_plan_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        NextCampaignIterationPlan.model_validate(_plan(client_slug="Bad Slug"))


def test_plan_version_pinned() -> None:
    with pytest.raises(ValidationError):
        NextCampaignIterationPlan.model_validate(
            _plan(contract_version="next-campaign-iteration-plan.v2")
        )


def test_plan_extra_field_rejected() -> None:
    data = _plan()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        NextCampaignIterationPlan.model_validate(data)


def test_plan_total_items_sums_correctly() -> None:
    actions = [
        IterationAction(
            kind=IterationActionKind.REPEAT_PIECE,
            priority=IterationActionPriority.HIGH,
            title="x", rationale="r", suggested_next_step="s",
        ).model_dump(mode="json"),
    ]
    ideas = [
        NewContentIdea(kind=NewContentKind.SEO_ARTICLE, title="t", rationale="r").model_dump(mode="json"),
    ]
    tests = [
        ABTestHypothesis(
            surface="x", variant_a="A", variant_b="B",
            success_metric="m", success_threshold="t", rationale="r",
        ).model_dump(mode="json"),
    ]
    calendar = [
        IterationCalendarEntry(week=1, channel="newsletter", piece_type="email").model_dump(mode="json"),
    ]
    tasks = [
        SuggestedIterationTask(
            title="t", category="seo",
            priority=IterationActionPriority.HIGH, rationale="r",
        ).model_dump(mode="json"),
    ]
    p = NextCampaignIterationPlan.model_validate(
        _plan(actions=actions, new_content_ideas=ideas,
              ab_test_hypotheses=tests, calendar=calendar,
              suggested_tasks=tasks)
    )
    assert p.total_items == 5
    assert len(p.actions_of_kind(IterationActionKind.REPEAT_PIECE)) == 1


def test_executive_summary_minimal() -> None:
    s = IterationExecutiveSummary(headline="hi")
    assert s.headline == "hi"


# ---------- Privacy ----------

def test_no_credential_fields() -> None:
    for cls in (
        IterationAction, NewContentIdea, ABTestHypothesis,
        IterationCalendarEntry, SuggestedIterationTask,
        IterationExecutiveSummary, NextCampaignIterationPlan,
    ):
        fields = set(cls.model_fields.keys())
        for forbidden in ("token", "api_key", "secret", "credential", "url", "webhook_url"):
            assert forbidden not in fields, (
                f"{cls.__name__}.{forbidden} would be a leak vector"
            )
