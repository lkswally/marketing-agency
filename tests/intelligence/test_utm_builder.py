"""Tests for core.intelligence.utm_builder (MKT-10X)."""

import json
from pathlib import Path

from core.intelligence.models import UTMPlan
from core.intelligence.utm_builder import (
    SINGLETON_ID,
    UTM_PLAN_KIND,
    UTMBuilder,
    _build_final_url,
    _slugify,
    persist_utm_plan,
)
from core.memory import JsonFileMemory
from core.strategy.backend import REPORT_KIND
from core.strategy.backend import SINGLETON_ID as STRATEGY_SINGLETON

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path / "mem")


def _strategy_report_fixture(client_slug: str) -> dict:
    """Minimal CampaignStrategyReport-shaped dict for testing."""
    return {
        "report_id": "fixture-report-001",
        "client_slug": client_slug,
        "executive_summary": {"campaign_name": "Test Campaign Summer"},
        "keyword_plan": {
            "clusters": [{"keywords": ["marketing software", "crm tool"]}]
        },
        "channel_recommendation": {
            "channels": [
                {"channel_type": "instagram", "rationale": "high audience overlap"},
                {"channel_type": "email", "rationale": "owned channel"},
                {"channel_type": "google_ads", "rationale": "high intent"},
            ],
            "total_channels": 3,
        },
        "suggested_pieces": [
            {"piece_type": "instagram_carousel", "channel": "instagram", "quantity": 4},
            {"piece_type": "email_welcome", "channel": "email", "quantity": 1},
            {"piece_type": "search_ad", "channel": "google_ads", "quantity": 3},
        ],
    }


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        result = _slugify("A & B (test)")
        # All non-alnum chars become hyphens; consecutive runs collapse
        assert result == result.lower()
        assert all(c.isalnum() or c == "-" for c in result)

    def test_max_len(self):
        result = _slugify("a" * 100, max_len=20)
        assert len(result) <= 20

    def test_already_slugified(self):
        assert _slugify("instagram-carousel") == "instagram-carousel"


class TestBuildFinalUrl:
    def test_no_existing_params(self):
        url = _build_final_url(
            "https://acme.com",
            {"utm_source": "instagram", "utm_medium": "social"},
        )
        assert "utm_source=instagram" in url
        assert "utm_medium=social" in url
        assert url.startswith("https://acme.com?")

    def test_existing_params(self):
        url = _build_final_url(
            "https://acme.com?ref=homepage",
            {"utm_source": "email"},
        )
        assert url.startswith("https://acme.com?ref=homepage&utm_source=email")

    def test_empty_values_excluded(self):
        url = _build_final_url(
            "https://acme.com",
            {"utm_source": "ig", "utm_term": ""},
        )
        assert "utm_term" not in url


# ---------------------------------------------------------------------------
# UTMBuilder — no strategy report (fallback plan)
# ---------------------------------------------------------------------------


class TestUTMBuilderFallback:
    def test_fallback_when_no_strategy(self, tmp_path):
        mem = _make_memory(tmp_path)
        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp")

        assert isinstance(plan, UTMPlan)
        assert plan.client_slug == "acme-corp"
        assert plan.total_links == 0
        assert plan.tagged_links == []
        assert len(plan.recommendations) >= 1
        assert plan.recommendations[0].priority == "high"
        assert "strategy" in plan.recommendations[0].description.lower()

    def test_fallback_period_default(self, tmp_path):
        mem = _make_memory(tmp_path)
        builder = UTMBuilder(mem)
        plan = builder.build("acme-corp")
        # Period should be YYYY-MM format
        assert len(plan.period) == 7
        assert plan.period[4] == "-"

    def test_fallback_custom_period(self, tmp_path):
        mem = _make_memory(tmp_path)
        builder = UTMBuilder(mem)
        plan = builder.build("acme-corp", period="2024-Q3")
        assert plan.period == "2024-Q3"


# ---------------------------------------------------------------------------
# UTMBuilder — with strategy report
# ---------------------------------------------------------------------------


class TestUTMBuilderWithStrategy:
    def test_generates_links_from_pieces(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        assert plan.total_links == len(report["suggested_pieces"])
        assert plan.total_links == 3
        assert plan.channels_covered  # non-empty

    def test_utm_source_derived_from_channel(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        sources = {lnk.utm_source for lnk in plan.tagged_links}
        assert "instagram" in sources or "email" in sources

    def test_search_channel_gets_utm_term(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        cpc_links = [lnk for lnk in plan.tagged_links if lnk.utm_medium == "cpc"]
        for lnk in cpc_links:
            assert lnk.utm_term is not None

    def test_final_url_contains_utm_params(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        for lnk in plan.tagged_links:
            assert "utm_source=" in lnk.final_url
            assert "utm_medium=" in lnk.final_url
            assert "utm_campaign=" in lnk.final_url

    def test_campaign_slug_contains_client_and_period(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        for lnk in plan.tagged_links:
            assert "acme" in lnk.utm_campaign
            assert "2024" in lnk.utm_campaign

    def test_channels_covered_list(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        assert isinstance(plan.channels_covered, list)
        assert len(plan.channels_covered) >= 1

    def test_recommendations_include_ga4(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        actions = [r.action for r in plan.recommendations]
        assert "configure_ga4_utm_dimensions" in actions


# ---------------------------------------------------------------------------
# persist_utm_plan
# ---------------------------------------------------------------------------


class TestPersistUtmPlan:
    def test_writes_output_files(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        outputs_root = tmp_path / "outputs"
        md_path, json_path = persist_utm_plan(plan, mem, outputs_root=outputs_root)

        assert md_path.exists()
        assert json_path.exists()

    def test_json_output_is_valid(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        outputs_root = tmp_path / "outputs"
        _, json_path = persist_utm_plan(plan, mem, outputs_root=outputs_root)

        data = json.loads(json_path.read_text())
        assert data["client_slug"] == "acme-corp"
        assert "tagged_links" in data

    def test_markdown_contains_table(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        outputs_root = tmp_path / "outputs"
        md_path, _ = persist_utm_plan(plan, mem, outputs_root=outputs_root)

        md = md_path.read_text()
        assert "# UTM Plan" in md
        assert "| Piece |" in md

    def test_persists_to_memory(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        persist_utm_plan(plan, mem, outputs_root=tmp_path / "outputs")

        stored = mem.get("acme-corp", UTM_PLAN_KIND, SINGLETON_ID)
        assert stored["client_slug"] == "acme-corp"

    def test_emits_audit_event(self, tmp_path):
        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("acme-corp")
        mem.put("acme-corp", REPORT_KIND, STRATEGY_SINGLETON, report)

        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        persist_utm_plan(plan, mem, outputs_root=tmp_path / "outputs")

        events = mem.read_audit_events("acme-corp")
        assert len(events) >= 1
        payloads = [e.payload for e in events]
        assert any(p.get("kind") == UTM_PLAN_KIND for p in payloads)

    def test_fallback_plan_also_persists(self, tmp_path):
        mem = _make_memory(tmp_path)
        builder = UTMBuilder(mem, base_url="https://acme.com")
        plan = builder.build("acme-corp", period="2024-06")

        persist_utm_plan(plan, mem, outputs_root=tmp_path / "outputs")
        stored = mem.get("acme-corp", UTM_PLAN_KIND, SINGLETON_ID)
        assert stored["total_links"] == 0


# ---------------------------------------------------------------------------
# CLI integration — utm-plan command
# ---------------------------------------------------------------------------


class TestUTMPlanCLI:
    def test_utm_plan_no_strategy(self, tmp_path):
        import io

        from cli.main import main

        root = str(tmp_path / "mem")
        outputs = str(tmp_path / "outputs")
        buf = io.StringIO()
        rc = main(
            ["utm-plan", "--client", "test-client", "--root", root, "--outputs-dir", outputs],
            out=buf,
        )
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert payload["status"] == "ok"
        assert payload["client_slug"] == "test-client"
        assert payload["total_links"] == 0

    def test_utm_plan_with_strategy(self, tmp_path):
        import io

        from cli.main import main

        mem = _make_memory(tmp_path)
        report = _strategy_report_fixture("lexia")
        mem.put("lexia", REPORT_KIND, STRATEGY_SINGLETON, report)

        root = str(tmp_path / "mem")
        outputs = str(tmp_path / "outputs")

        buf = io.StringIO()
        rc = main(
            [
                "utm-plan",
                "--client", "lexia",
                "--root", root,
                "--outputs-dir", outputs,
                "--base-url", "https://lexia.com",
                "--period", "2024-06",
            ],
            out=buf,
        )
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert payload["total_links"] >= 1
        assert Path(payload["utm_plan_md"]).exists()
        assert Path(payload["utm_plan_json"]).exists()
