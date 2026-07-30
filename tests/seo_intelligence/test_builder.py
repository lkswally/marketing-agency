"""Tests for SEOIntelligenceReportBuilder (MKT-10C).

Covers the 13 minimum test categories from the MKT-10C spec:
1. Full report with GA4 + Search Console.
2. Report with no metrics.
3. Fact vs hypothesis separation.
4. Missing evidence is visible.
5. Multi-tenant persistence.
6. Different periods do not collide.
7. 'current' alias.
8. Markdown output.
9. JSON output.
10. Audit trail.
11. CLI (see tests/cli/test_seo_report_cli.py).
12. Determinism.
13. Protection against invented data.
"""

from __future__ import annotations

from datetime import date

from core.analytics import METRICS_SNAPSHOT_KIND
from core.analytics.models import SINGLETON_ID as SNAPSHOT_SINGLETON_ID
from core.analytics.models import MetricRow, MetricSource, MetricsSnapshot
from core.domain.base import utcnow
from core.memory import JsonFileMemory
from core.seo_intelligence import (
    SEO_INTELLIGENCE_REPORT_PACK_KIND,
    SINGLETON_ID,
    FindingNature,
    KeywordResearchRow,
    LocaleInput,
    SEOEvidenceInput,
    SEOIntelligenceReportBuilder,
    SEOIntelligenceReportPack,
    render_markdown_seo_report,
)
from core.seo_intelligence.builder import report_entity_id


def _mem(tmp_path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path / "mem")


def _put_snapshot(mem: JsonFileMemory, client: str, rows: list[MetricRow]) -> None:
    snap = MetricsSnapshot(
        client_slug=client, rows=rows, created_at=utcnow(), updated_at=utcnow(),
    )
    mem.put(client, METRICS_SNAPSHOT_KIND, SNAPSHOT_SINGLETON_ID, snap.model_dump(mode="json"))


def _full_evidence(client: str) -> SEOEvidenceInput:
    return SEOEvidenceInput(
        client_slug=client,
        keyword_research=[
            KeywordResearchRow(keyword="crm legal", search_intent="transactional", search_volume=100),
            KeywordResearchRow(keyword="qué es un crm", search_intent="informational", search_volume=50),
        ],
        url_structure=["/es/blog/a", "/es/blog/b"],
        locales=[LocaleInput(locale="es-AR", is_active=True)],
        technical_notes=[
            "canonical tags missing on /blog/*",
            "noindex found on /search",
            "thin content on /es/pricing",
        ],
    )


def _ga4_gsc_rows() -> list[MetricRow]:
    return [
        MetricRow(source=MetricSource.SEARCH_CONSOLE, metric_name="impressions", value=5000),
        MetricRow(source=MetricSource.SEARCH_CONSOLE, metric_name="clicks", value=50),
        MetricRow(source=MetricSource.SEARCH_CONSOLE, metric_name="position", value=25),
        MetricRow(source=MetricSource.GA4, metric_name="sessions", value=1000, channel="organic"),
        MetricRow(source=MetricSource.GA4, metric_name="sessions", value=3000, channel="paid"),
    ]


# ---------- 1. Full report with GA4 + Search Console ----------

def test_full_report_with_ga4_and_search_console(tmp_path) -> None:
    mem = _mem(tmp_path)
    _put_snapshot(mem, "acme", _ga4_gsc_rows())
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme", evidence_input=_full_evidence("acme"))

    assert pack.snapshot_id is not None
    assert pack.organic_performance_findings  # non-empty — real metrics present
    assert pack.executive_summary.facts_count > 0
    assert pack.keyword_clusters  # non-empty — keyword research supplied


# ---------- 2. Report with no metrics ----------

def test_report_with_no_metrics(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme")

    assert pack.snapshot_id is None
    assert pack.organic_performance_findings == []
    assert any(
        m.description.lower().find("metricssnapshot") != -1
        for m in pack.missing_evidence
    )


# ---------- 3. Fact vs hypothesis separation ----------

def test_facts_and_hypotheses_are_separated(tmp_path) -> None:
    mem = _mem(tmp_path)
    _put_snapshot(mem, "acme", _ga4_gsc_rows())
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme", evidence_input=_full_evidence("acme"))

    natures = {f.nature for f in pack.organic_performance_findings}
    assert FindingNature.FACT in natures
    assert FindingNature.HYPOTHESIS in natures
    # Canonical/indexation risks are HYPOTHESIS-nature by construction.
    assert all(r.nature == FindingNature.HYPOTHESIS for r in pack.canonical_risks)
    assert all(r.nature == FindingNature.HYPOTHESIS for r in pack.indexation_risks)
    # A fact must cite a metric; a pure hypothesis need not.
    facts = [f for f in pack.organic_performance_findings if f.nature == FindingNature.FACT]
    assert all(f.metrics_cited for f in facts)


# ---------- 4. Missing evidence is visible ----------

def test_missing_evidence_is_visible(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme")

    assert len(pack.missing_evidence) > 0
    categories = {m.category for m in pack.missing_evidence}
    assert len(categories) > 1  # multiple distinct gaps, not one blob


# ---------- 5. Multi-tenant persistence ----------

def test_multi_tenant_persistence_does_not_cross_contaminate(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)

    _put_snapshot(mem, "acme", _ga4_gsc_rows())
    pack_acme = builder.build("acme", evidence_input=_full_evidence("acme"))
    builder.persist(pack_acme)

    pack_other = builder.build("other-client")
    builder.persist(pack_other)

    raw_acme = mem.get("acme", SEO_INTELLIGENCE_REPORT_PACK_KIND, SINGLETON_ID)
    raw_other = mem.get("other-client", SEO_INTELLIGENCE_REPORT_PACK_KIND, SINGLETON_ID)
    assert raw_acme["client_slug"] == "acme"
    assert raw_other["client_slug"] == "other-client"
    assert raw_acme["report_id"] != raw_other["report_id"]
    assert len(raw_acme["organic_performance_findings"]) > 0
    assert len(raw_other["organic_performance_findings"]) == 0


# ---------- 6. Different periods do not collide ----------

def test_different_periods_do_not_collide(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)

    p1_start, p1_end = date(2026, 1, 1), date(2026, 1, 31)
    p2_start, p2_end = date(2026, 2, 1), date(2026, 2, 28)

    pack1 = builder.build("acme", period_start=p1_start, period_end=p1_end, period_label="2026-01")
    builder.persist(pack1)
    pack2 = builder.build("acme", period_start=p2_start, period_end=p2_end, period_label="2026-02")
    builder.persist(pack2)

    eid1 = report_entity_id("acme", p1_start, p1_end)
    eid2 = report_entity_id("acme", p2_start, p2_end)
    assert eid1 != eid2

    raw1 = mem.get("acme", SEO_INTELLIGENCE_REPORT_PACK_KIND, eid1)
    raw2 = mem.get("acme", SEO_INTELLIGENCE_REPORT_PACK_KIND, eid2)
    assert raw1["period_label"] == "2026-01"
    assert raw2["period_label"] == "2026-02"
    assert raw1["report_id"] != raw2["report_id"]


# ---------- 7. 'current' alias ----------

def test_current_alias_always_written(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build(
        "acme", period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
    )
    builder.persist(pack)

    current = mem.get("acme", SEO_INTELLIGENCE_REPORT_PACK_KIND, SINGLETON_ID)
    assert current["client_slug"] == "acme"
    eid = report_entity_id("acme", date(2026, 1, 1), date(2026, 1, 31))
    period_raw = mem.get("acme", SEO_INTELLIGENCE_REPORT_PACK_KIND, eid)
    # Same content (dual-write), different persisted entity ids.
    assert current["report_id"] == period_raw["report_id"]


# ---------- 8. Markdown output ----------

def test_markdown_render_contains_all_20_sections(tmp_path) -> None:
    mem = _mem(tmp_path)
    _put_snapshot(mem, "acme", _ga4_gsc_rows())
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme", evidence_input=_full_evidence("acme"))
    md = render_markdown_seo_report(pack)

    for heading in [
        "1. Resumen ejecutivo", "2. Estado de la evidencia",
        "3-4. Keyword research", "5. Rendimiento orgánico",
        "6. Arquitectura de páginas", "7. Canonicalización",
        "8. Indexación", "9. Thin content", "10. Enlazado interno",
        "11. Contenido y clusters", "12. Países, idiomas y locales",
        "13. Competidores", "14. Riesgos", "15. Oportunidades",
        "16. Roadmap por fases", "17-18. Gaps para desarrollo",
        "19. Datos faltantes", "20. Próximas decisiones requeridas",
    ]:
        assert heading in md, f"missing section: {heading}"


# ---------- 9. JSON output ----------

def test_json_round_trip(tmp_path) -> None:
    mem = _mem(tmp_path)
    _put_snapshot(mem, "acme", _ga4_gsc_rows())
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme", evidence_input=_full_evidence("acme"))

    payload = pack.to_json()
    restored = SEOIntelligenceReportPack.from_json(payload)
    assert restored.report_id == pack.report_id
    assert restored.client_slug == pack.client_slug
    assert len(restored.organic_performance_findings) == len(pack.organic_performance_findings)


# ---------- 10. Audit trail ----------

def test_persist_writes_audit_event(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme")
    builder.persist(pack)

    events = mem.read_audit_events("acme")
    assert len(events) == 1
    payload = events[0].payload["seo_intelligence_report_pack"]
    assert payload["action"] == "built"
    assert payload["report_id"] == pack.report_id
    assert payload["missing_evidence_count"] == len(pack.missing_evidence)


# ---------- 12. Determinism ----------

def test_build_is_deterministic_given_same_inputs(tmp_path) -> None:
    mem = _mem(tmp_path)
    _put_snapshot(mem, "acme", _ga4_gsc_rows())
    evidence = _full_evidence("acme")
    builder = SEOIntelligenceReportBuilder(memory=mem)

    pack1 = builder.build("acme", evidence_input=evidence)
    pack2 = builder.build("acme", evidence_input=evidence)

    # IDs are randomly generated per call, but the substantive content —
    # counts, statements, ordering — must be identical.
    assert pack1.executive_summary.facts_count == pack2.executive_summary.facts_count
    assert pack1.executive_summary.hypotheses_count == pack2.executive_summary.hypotheses_count
    assert [f.statement for f in pack1.organic_performance_findings] == (
        [f.statement for f in pack2.organic_performance_findings]
    )
    assert [c.label for c in pack1.keyword_clusters] == [c.label for c in pack2.keyword_clusters]
    assert len(pack1.missing_evidence) == len(pack2.missing_evidence)


# ---------- 13. Protection against invented data ----------

def test_no_organic_performance_findings_without_snapshot(tmp_path) -> None:
    """No GA4/Search Console rows → zero organic-performance FACTS,
    never a fabricated metric."""
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme", evidence_input=_full_evidence("acme"))

    assert pack.organic_performance_findings == []
    assert any(
        m.category.value == "organic_performance" for m in pack.missing_evidence
    )


def test_no_competitor_finding_without_competitor_data(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    pack = builder.build("acme")

    assert pack.competitor_findings == []
    assert any(m.category.value == "competitors" for m in pack.missing_evidence)


def test_no_keyword_clusters_without_keyword_research(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    evidence = SEOEvidenceInput(client_slug="acme")  # no keyword_research
    pack = builder.build("acme", evidence_input=evidence)

    assert pack.keyword_clusters == []
    assert any(m.category.value == "keyword_research" for m in pack.missing_evidence)


def test_internal_link_opportunity_requires_at_least_two_urls(tmp_path) -> None:
    mem = _mem(tmp_path)
    builder = SEOIntelligenceReportBuilder(memory=mem)
    evidence = SEOEvidenceInput(client_slug="acme", url_structure=["/only-one"])
    pack = builder.build("acme", evidence_input=evidence)

    assert pack.internal_link_opportunities == []
