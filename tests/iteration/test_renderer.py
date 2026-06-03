"""Renderer tests for the iteration plan."""

from __future__ import annotations

from datetime import UTC, date, datetime

from core.iteration import (
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
    render_markdown_iteration_plan,
)
from core.iteration.models import SuggestedIterationTask


def _plan(**overrides) -> NextCampaignIterationPlan:
    base = dict(
        client_slug="acme-saas",
        feedback_pack_id="fb1",
        feedback_pack_contract_version="campaign-feedback-pack.v1",
        executive_summary=IterationExecutiveSummary(
            headline="Headline test",
            paragraphs=["p1", "p2"],
            suggested_meeting_agenda=["item 1", "item 2"],
        ),
        actions=[
            IterationAction(
                kind=IterationActionKind.REPEAT_PIECE,
                priority=IterationActionPriority.HIGH,
                title="Repeat post-001",
                channel="linkedin",
                target_ref="post-001",
                rationale="top performer",
                suggested_next_step="replicate",
            ),
            IterationAction(
                kind=IterationActionKind.CHANNEL_PAUSE,
                priority=IterationActionPriority.MEDIUM,
                title="Pause x",
                channel="x",
                rationale="zero engagement",
                suggested_next_step="pause 4 weeks",
            ),
        ],
        new_content_ideas=[
            NewContentIdea(
                kind=NewContentKind.SEO_ARTICLE,
                title="SEO article on marketing pipeline",
                channel="organic_search",
                rationale="opportunity",
                angle="cover intent + linking",
                priority=IterationActionPriority.HIGH,
            ),
        ],
        ab_test_hypotheses=[
            ABTestHypothesis(
                surface="email_subject",
                variant_a="A",
                variant_b="B",
                success_metric="open_rate",
                success_threshold="uplift >= 20%",
                rationale="low opens",
            ),
        ],
        calendar=[
            IterationCalendarEntry(
                week=1, suggested_date=date(2026, 7, 1),
                channel="linkedin", piece_type="post",
                note="repeat post-001",
            ),
        ],
        suggested_tasks=[
            SuggestedIterationTask(
                title="run import next cycle",
                category="measurement",
                priority=IterationActionPriority.MEDIUM,
                rationale="loop",
                suggested_owner="analytics_lead",
            ),
        ],
        stats=IterationStats(
            total_actions=2, repeats=1, pauses=0, improves=0, creates=0,
            channel_adjustments=1,
            new_content_ideas=1, ab_test_hypotheses=1,
            calendar_entries=1, suggested_tasks=1,
        ),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return NextCampaignIterationPlan(**base)


def test_renders_all_sections() -> None:
    md = render_markdown_iteration_plan(_plan())
    for section in (
        "Next Campaign Iteration Plan",
        "01. Resumen ejecutivo",
        "02. Estadísticas",
        "03. Acciones",
        "04. Ideas de contenido",
        "05. Hipótesis A/B",
        "06. Calendario sugerido",
        "07. Tareas sugeridas",
        "08. Agenda sugerida",
    ):
        assert section in md


def test_repeat_action_uses_emoji() -> None:
    md = render_markdown_iteration_plan(_plan())
    assert "🔁" in md
    assert "Repeat post-001" in md


def test_channel_pause_action_rendered() -> None:
    md = render_markdown_iteration_plan(_plan())
    assert "channel_pause" in md
    assert "Pause x" in md


def test_ab_test_section_shows_variants() -> None:
    md = render_markdown_iteration_plan(_plan())
    assert "A (control)" in md
    assert "B (variante)" in md
    assert "uplift >= 20%" in md


def test_calendar_table_rendered() -> None:
    md = render_markdown_iteration_plan(_plan())
    assert "2026-07-01" in md
    assert "`linkedin`" in md


def test_footer_says_no_external_api() -> None:
    md = render_markdown_iteration_plan(_plan())
    assert "sin LLM" in md
    assert "sin API externa" in md
    assert "una persona" in md


def test_renderer_is_pure() -> None:
    p = _plan()
    a = render_markdown_iteration_plan(p)
    b = render_markdown_iteration_plan(p)
    assert a == b


def test_renderer_handles_empty_plan() -> None:
    empty = NextCampaignIterationPlan(
        client_slug="acme",
        feedback_pack_id="fb1",
        feedback_pack_contract_version="campaign-feedback-pack.v1",
        stats=IterationStats(
            total_actions=0, repeats=0, pauses=0, improves=0, creates=0,
            channel_adjustments=0, new_content_ideas=0,
            ab_test_hypotheses=0, calendar_entries=0, suggested_tasks=0,
        ),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    md = render_markdown_iteration_plan(empty)
    assert "(sin acciones para el próximo ciclo)" in md
    assert "(sin ideas)" in md
    assert "(sin tests propuestos)" in md
    assert "(sin calendario)" in md
    assert "(sin tareas)" in md
