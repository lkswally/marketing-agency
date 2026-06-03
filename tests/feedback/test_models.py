"""Pydantic validation tests for the campaign feedback pack."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.feedback import (
    CAMPAIGN_FEEDBACK_PACK_VERSION,
    CampaignFeedbackPack,
    ChannelAdjustment,
    ChannelPriority,
    ContentSuggestion,
    ContentSuggestionKind,
    EmailRecommendation,
    ExecutiveSummary,
    FeedbackStats,
    SEORecommendation,
    SocialRecommendation,
    SuggestedTask,
    SuggestedTaskCategory,
    SuggestedTaskPriority,
)


def _now() -> datetime:
    return datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _stats(**overrides) -> FeedbackStats:
    base = dict(
        total_suggested_tasks=0,
        high_priority_tasks=0,
        channel_adjustments=0,
        content_suggestions=0,
        seo_recommendations=0,
        email_recommendations=0,
        social_recommendations=0,
    )
    base.update(overrides)
    return FeedbackStats(**base)


def _pack(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "stats": _stats().model_dump(mode="json"),
        "created_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


# ---------- SuggestedTask ----------

def test_suggested_task_minimal() -> None:
    t = SuggestedTask(
        title="Repetir linkedin",
        category=SuggestedTaskCategory.OPTIMIZATION,
        priority=SuggestedTaskPriority.HIGH,
        rationale="r",
    )
    assert t.category is SuggestedTaskCategory.OPTIMIZATION
    assert t.evidence_refs == []


def test_suggested_task_invalid_category() -> None:
    with pytest.raises(ValidationError):
        SuggestedTask(
            title="x",
            category="invented",  # type: ignore[arg-type]
            priority=SuggestedTaskPriority.HIGH,
            rationale="r",
        )


# ---------- ChannelAdjustment ----------

def test_channel_adjustment_with_pause() -> None:
    a = ChannelAdjustment(
        channel="x",
        new_priority=ChannelPriority.PAUSE,
        rationale="zero engagement",
    )
    assert a.new_priority is ChannelPriority.PAUSE
    assert a.current_priority is None


def test_channel_adjustment_all_priorities() -> None:
    for p in ChannelPriority:
        ChannelAdjustment(channel="c", new_priority=p, rationale="r")


# ---------- ContentSuggestion ----------

def test_content_suggestion_kinds() -> None:
    for k in ContentSuggestionKind:
        ContentSuggestion(
            kind=k, title="t", rationale="r",
            suggested_next_step="step",
        )


# ---------- CampaignFeedbackPack ----------

def test_minimal_pack_validates() -> None:
    p = CampaignFeedbackPack.model_validate(_pack())
    assert p.contract_version == CAMPAIGN_FEEDBACK_PACK_VERSION
    assert p.total_items == 0


def test_pack_round_trip() -> None:
    p = CampaignFeedbackPack.model_validate(_pack())
    reloaded = CampaignFeedbackPack.from_json(p.to_json())
    assert reloaded.model_dump() == p.model_dump()


def test_pack_naive_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignFeedbackPack.model_validate(_pack(created_at="2026-06-02T12:00:00"))


def test_pack_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignFeedbackPack.model_validate(_pack(client_slug="Bad Slug"))


def test_pack_version_pinned() -> None:
    with pytest.raises(ValidationError):
        CampaignFeedbackPack.model_validate(
            _pack(contract_version="campaign-feedback-pack.v2")
        )


def test_pack_extra_field_rejected() -> None:
    data = _pack()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        CampaignFeedbackPack.model_validate(data)


def test_pack_total_items_sums_correctly() -> None:
    tasks = [
        SuggestedTask(
            title="t", category=SuggestedTaskCategory.SEO,
            priority=SuggestedTaskPriority.HIGH, rationale="r",
        ).model_dump(mode="json"),
        SuggestedTask(
            title="t2", category=SuggestedTaskCategory.EMAIL,
            priority=SuggestedTaskPriority.LOW, rationale="r",
        ).model_dump(mode="json"),
    ]
    adjustments = [
        ChannelAdjustment(
            channel="x", new_priority=ChannelPriority.PAUSE, rationale="r",
        ).model_dump(mode="json"),
    ]
    p = CampaignFeedbackPack.model_validate(
        _pack(suggested_tasks=tasks, channel_adjustments=adjustments)
    )
    assert p.total_items == 3
    assert len(p.tasks_by_category(SuggestedTaskCategory.SEO)) == 1


def test_executive_summary_minimal() -> None:
    s = ExecutiveSummary(headline="hi", paragraphs=["p1"])
    assert s.headline == "hi"


# ---------- Privacy ----------

def test_models_have_no_credential_or_url_fields() -> None:
    for cls in (
        SuggestedTask, ChannelAdjustment, ContentSuggestion,
        SEORecommendation, EmailRecommendation, SocialRecommendation,
        ExecutiveSummary, CampaignFeedbackPack,
    ):
        fields = set(cls.model_fields.keys())
        for forbidden in ("token", "api_key", "secret", "credential", "url", "webhook_url"):
            assert forbidden not in fields, (
                f"{cls.__name__}.{forbidden} would be a leak vector"
            )
