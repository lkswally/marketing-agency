"""Renderer tests for the campaign feedback pack."""

from __future__ import annotations

from datetime import UTC, datetime

from core.feedback import (
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
    render_markdown_feedback,
)


def _pack(**overrides) -> CampaignFeedbackPack:
    base = dict(
        client_slug="acme-saas",
        recommendation_pack_id="r1",
        executive_summary=ExecutiveSummary(
            headline="Headline test",
            paragraphs=["p1", "p2"],
            suggested_meeting_agenda=["item 1", "item 2"],
        ),
        suggested_tasks=[
            SuggestedTask(
                title="repeat linkedin",
                category=SuggestedTaskCategory.OPTIMIZATION,
                priority=SuggestedTaskPriority.HIGH,
                rationale="bla",
                suggested_owner="account_lead",
            ),
        ],
        channel_adjustments=[
            ChannelAdjustment(
                channel="linkedin",
                current_priority=ChannelPriority.MEDIUM,
                new_priority=ChannelPriority.HIGH,
                rationale="best performer",
            ),
            ChannelAdjustment(
                channel="x",
                new_priority=ChannelPriority.PAUSE,
                rationale="zero engagement",
            ),
        ],
        content_suggestions=[
            ContentSuggestion(
                kind=ContentSuggestionKind.REPEAT,
                content_ref="post-001",
                channel="linkedin",
                title="repeat post-001",
                rationale="top engagement",
                suggested_next_step="replicate hook",
            ),
        ],
        seo_recommendations=[
            SEORecommendation(
                query="marketing pipeline",
                page="/blog/intro",
                priority=SuggestedTaskPriority.HIGH,
                suggested_action="revisar meta",
                rationale="low ctr",
                opportunity_score=60.0,
            ),
        ],
        email_recommendations=[
            EmailRecommendation(
                campaign_ref="email-002",
                open_rate=0.18,
                click_rate=None,
                suggested_action="A/B test subject",
                rationale="open rate bajo",
                priority=SuggestedTaskPriority.HIGH,
            ),
        ],
        social_recommendations=[
            SocialRecommendation(
                channel="x",
                content_ref="post-002",
                suggested_action="reformular hook",
                rationale="low engagement",
                priority=SuggestedTaskPriority.MEDIUM,
            ),
        ],
        stats=FeedbackStats(
            total_suggested_tasks=1,
            high_priority_tasks=1,
            channel_adjustments=2,
            content_suggestions=1,
            seo_recommendations=1,
            email_recommendations=1,
            social_recommendations=1,
        ),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return CampaignFeedbackPack(**base)


def test_renders_all_sections() -> None:
    md = render_markdown_feedback(_pack())
    for section in (
        "Campaign Feedback Pack",
        "01. Resumen ejecutivo",
        "02. Estadísticas",
        "03. Ajustes de canal",
        "04. Sugerencias de contenido",
        "05. SEO",
        "06. Email",
        "07. Social",
        "08. Tareas sugeridas",
        "09. Agenda sugerida",
    ):
        assert section in md


def test_executive_summary_paragraphs_rendered() -> None:
    md = render_markdown_feedback(_pack())
    assert "Headline test" in md
    assert "> p1" in md
    assert "> p2" in md


def test_pause_emoji_for_pause_priority() -> None:
    md = render_markdown_feedback(_pack())
    assert "⏸️" in md
    assert "`pause`" in md


def test_seo_table_uses_scores() -> None:
    md = render_markdown_feedback(_pack())
    assert "60.0" in md  # opportunity_score
    assert "marketing pipeline" in md


def test_email_open_rate_formatted() -> None:
    md = render_markdown_feedback(_pack())
    assert "18.0%" in md  # 0.18 → 18.0%


def test_social_section_shows_channel() -> None:
    md = render_markdown_feedback(_pack())
    assert "`x`" in md  # social channel
    assert "post-002" in md


def test_footer_says_no_external_api() -> None:
    md = render_markdown_feedback(_pack())
    assert "sin LLM" in md
    assert "sin API externa" in md
    assert "una persona" in md


def test_renderer_is_pure() -> None:
    p = _pack()
    a = render_markdown_feedback(p)
    b = render_markdown_feedback(p)
    assert a == b


def test_renderer_handles_empty_sections() -> None:
    empty = CampaignFeedbackPack(
        client_slug="acme",
        stats=FeedbackStats(
            total_suggested_tasks=0,
            high_priority_tasks=0,
            channel_adjustments=0,
            content_suggestions=0,
            seo_recommendations=0,
            email_recommendations=0,
            social_recommendations=0,
        ),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    md = render_markdown_feedback(empty)
    assert "(sin ajustes)" in md
    assert "(sin sugerencias)" in md
    assert "(sin oportunidades detectadas)" in md
    assert "(sin tareas)" in md
