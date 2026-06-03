"""AnalyticsAnalyzer tests — heuristics + recommendations."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.analytics import (
    OPTIMIZATION_RECOMMENDATION_PACK_KIND,
    SINGLETON_ID,
    AnalyticsAnalyzer,
    AnalyticsImporter,
    MetricSource,
)
from core.analytics.models import RecommendationKind, RecommendationPriority
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"


def _import_all(mem: JsonFileMemory, client: str) -> None:
    importer = AnalyticsImporter(memory=mem)
    pairs = [
        (FIXTURES / "ga4_demo.csv", MetricSource.GA4),
        (FIXTURES / "sc_demo.csv", MetricSource.SEARCH_CONSOLE),
        (FIXTURES / "social_demo.csv", MetricSource.SOCIAL),
        (FIXTURES / "email_demo.csv", MetricSource.EMAIL),
    ]
    for path, src in pairs:
        importer.import_file(client_slug=client, source=src, file_path=path)


# ---------- happy path ----------

def test_analyze_emits_pack(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    assert pack.client_slug == "acme"
    assert pack.total_rows_analyzed > 30
    assert pack.channels  # non-empty
    assert pack.best_channel
    assert pack.recommendations


def test_best_channel_picked_from_clicks_plus_conversions(tmp_path: Path) -> None:
    """The social fixture has linkedin with 270 clicks and x with
    near-zero; linkedin should win."""
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    assert pack.best_channel == "linkedin"


def test_worst_channel_is_high_impressions_low_engagement(tmp_path: Path) -> None:
    """x has 3000 impressions and only 1 click → worst channel."""
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    assert pack.worst_channel == "x"


def test_seo_opportunities_detected(tmp_path: Path) -> None:
    """SC fixture has rows with low CTR or low position above 10."""
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    opps = pack.seo_opportunities.opportunities
    assert opps
    # Top opp has a meaningful score.
    assert opps[0].opportunity_score > 0


def test_recommendations_include_repeat_pause_seo(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    kinds = {r.kind for r in pack.recommendations}
    assert RecommendationKind.REPEAT in kinds
    assert RecommendationKind.PAUSE in kinds
    assert RecommendationKind.SEO_OPPORTUNITY in kinds


def test_repeat_recommendation_is_high_priority(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    repeat = next(
        r for r in pack.recommendations if r.kind is RecommendationKind.REPEAT
    )
    assert repeat.priority is RecommendationPriority.HIGH
    assert "linkedin" in repeat.evidence_refs[0]


def test_top_content_ranked_first_has_most_engagement(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    if pack.top_content:
        first = pack.top_content[0]
        for c in pack.top_content[1:]:
            assert (
                first.total_clicks + first.total_engagement + first.total_conversions
                >= c.total_clicks + c.total_engagement + c.total_conversions
            )


def test_next_actions_are_emitted(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    pack = AnalyticsAnalyzer(memory=mem).analyze("acme")
    assert pack.next_actions  # at least one
    assert all(isinstance(a, str) and a for a in pack.next_actions)


# ---------- no snapshot ----------

def test_missing_snapshot_raises(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    with pytest.raises(ValueError):
        AnalyticsAnalyzer(memory=mem).analyze("nonexistent")


# ---------- determinism ----------

def test_two_analyses_produce_same_rankings(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    a = AnalyticsAnalyzer(memory=mem).analyze("acme")
    b = AnalyticsAnalyzer(memory=mem).analyze("acme")
    assert a.best_channel == b.best_channel
    assert a.worst_channel == b.worst_channel
    assert [c.channel for c in a.channels] == [c.channel for c in b.channels]


# ---------- persistence + audit ----------

def test_persist_writes_to_memory(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    analyzer = AnalyticsAnalyzer(memory=mem)
    pack = analyzer.analyze("acme")
    analyzer.persist(pack)
    assert mem.exists("acme", OPTIMIZATION_RECOMMENDATION_PACK_KIND, SINGLETON_ID)
    loaded = analyzer.load_latest("acme")
    assert loaded.pack_id == pack.pack_id


def test_persist_emits_audit_event(tmp_path: Path) -> None:
    mem = JsonFileMemory(tmp_path / "mem")
    _import_all(mem, "acme")
    analyzer = AnalyticsAnalyzer(memory=mem)
    analyzer.persist(analyzer.analyze("acme"))
    events = mem.read_audit_events("acme")
    actions = [
        e.payload.get("analytics_analysis", {}).get("action")
        for e in events
        if "analytics_analysis" in e.payload
    ]
    assert "analyzed" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []


# ---------- safety ----------

def test_analyzer_does_not_import_http_or_env() -> None:
    import inspect

    import core.analytics.analyzer as mod
    src = inspect.getsource(mod)
    for forbidden in (
        "import requests", "import httpx", "urllib.request",
        "os.environ", "import anthropic",
    ):
        assert forbidden not in src


def test_pack_has_no_credential_fields() -> None:
    from core.analytics import OptimizationRecommendationPack
    fields = set(OptimizationRecommendationPack.model_fields.keys())
    for forbidden in ("token", "api_key", "secret", "credential", "url"):
        assert forbidden not in fields
