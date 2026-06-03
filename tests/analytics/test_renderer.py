"""Renderer tests for the analytics markdown outputs."""

from __future__ import annotations

from datetime import UTC, datetime

from core.analytics import (
    AnalyticsImportReport,
    ChannelPerformanceSummary,
    ContentPerformanceSummary,
    MetricSource,
    OptimizationRecommendationPack,
    Recommendation,
    SEOOpportunity,
    SEOOpportunityReport,
    render_markdown_import_report,
    render_markdown_recommendations,
)
from core.analytics.models import RecommendationKind, RecommendationPriority


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


# ---------- import report renderer ----------

def test_import_report_header() -> None:
    r = AnalyticsImportReport(
        client_slug="acme",
        source=MetricSource.GA4,
        file_path="/tmp/x.csv",
        rows_imported=10,
        rows_rejected=2,
        rejected_reasons=["row 1: missing channel"],
        imported_at=_now(),
    )
    md = render_markdown_import_report(r)
    assert "Analytics Import Report" in md
    assert "ga4" in md
    assert "Filas importadas: `10`" in md
    assert "Filas rechazadas: `2`" in md
    assert "row 1: missing channel" in md


def test_import_report_no_rejection_section_when_clean() -> None:
    r = AnalyticsImportReport(
        client_slug="acme",
        source=MetricSource.MANUAL,
        file_path="/tmp/x.csv",
        rows_imported=5,
        rows_rejected=0,
        imported_at=_now(),
    )
    md = render_markdown_import_report(r)
    assert "Razones de rechazo" not in md


# ---------- recommendation pack renderer ----------

def _pack(**overrides) -> OptimizationRecommendationPack:
    base = dict(
        client_slug="acme",
        snapshot_id="s1",
        snapshot_contract_version="metrics-snapshot.v1",
        total_rows_analyzed=42,
        channels=[
            ChannelPerformanceSummary(
                channel="linkedin", total_clicks=270, total_impressions=13500,
                total_engagement=680, sample_rows=2,
            ),
            ChannelPerformanceSummary(
                channel="x", total_clicks=1, total_impressions=3000,
                total_engagement=30, sample_rows=1,
            ),
        ],
        top_content=[
            ContentPerformanceSummary(
                content_ref="post-001", channel="linkedin",
                total_clicks=180, total_engagement=420, sample_rows=1,
            )
        ],
        seo_opportunities=SEOOpportunityReport(
            opportunities=[
                SEOOpportunity(
                    query="marketing pipeline", page="/blog/intro",
                    impressions=2000, clicks=40, ctr=0.02, position=11,
                    opportunity_score=60.0, reason="CTR bajo",
                )
            ]
        ),
        best_channel="linkedin",
        worst_channel="x",
        recommendations=[
            Recommendation(
                kind=RecommendationKind.REPEAT,
                priority=RecommendationPriority.HIGH,
                title="Repetir linkedin",
                rationale="bla",
                suggested_action="hacer X",
                evidence_refs=["channel:linkedin"],
            ),
            Recommendation(
                kind=RecommendationKind.PAUSE,
                priority=RecommendationPriority.MEDIUM,
                title="Pausar x",
                rationale="bla",
                suggested_action="pausar",
            ),
        ],
        next_actions=["Asignar share a linkedin", "Pausar x"],
        created_at=_now(),
    )
    base.update(overrides)
    return OptimizationRecommendationPack(**base)


def test_pack_renderer_sections() -> None:
    md = render_markdown_recommendations(_pack())
    for section in (
        "Optimization Recommendation Pack",
        "## 01. Resumen",
        "## 02. Canales",
        "## 03. Top content",
        "## 04. SEO opportunities",
        "## 05. Recomendaciones",
        "## 06. Próximas acciones",
    ):
        assert section in md


def test_pack_renderer_shows_best_and_worst_channel() -> None:
    md = render_markdown_recommendations(_pack())
    assert "Mejor canal**: `linkedin`" in md
    assert "Peor canal**: `x`" in md


def test_pack_renderer_recommendations_sorted_by_priority() -> None:
    md = render_markdown_recommendations(_pack())
    high_idx = md.find("🔴 `high`")
    med_idx = md.find("🟠 `medium`")
    assert 0 <= high_idx < med_idx


def test_pack_renderer_pure() -> None:
    p = _pack()
    a = render_markdown_recommendations(p)
    b = render_markdown_recommendations(p)
    assert a == b


def test_pack_renderer_handles_empty_pack() -> None:
    p = OptimizationRecommendationPack(
        client_slug="acme",
        snapshot_id="s1",
        snapshot_contract_version="metrics-snapshot.v1",
        total_rows_analyzed=0,
        created_at=_now(),
    )
    md = render_markdown_recommendations(p)
    assert "(sin datos de canal)" in md
    assert "(sin oportunidades detectadas)" in md
    assert "(sin recomendaciones)" in md


def test_footer_says_no_external_api() -> None:
    md = render_markdown_recommendations(_pack())
    assert "sin LLM" in md
    assert "sin API externa" in md
