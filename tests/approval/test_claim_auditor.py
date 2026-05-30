"""Claim auditor tests — rule firing + report walking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.approval import (
    DEFAULT_RULE_SET_ID,
    DEFAULT_RULES,
    ClaimAuditor,
    ClaimCategory,
    ClaimRule,
)
from core.domain.enums import ClaimSeverity
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def auditor() -> ClaimAuditor:
    return ClaimAuditor()


# ---------- Rule set hygiene ----------

def test_default_rule_set_loaded(auditor: ClaimAuditor) -> None:
    assert len(auditor.rules) >= 20
    assert auditor.rule_set_id == DEFAULT_RULE_SET_ID
    # No duplicate rule_ids.
    ids = [r.rule_id for r in auditor.rules]
    assert len(ids) == len(set(ids))


def test_every_default_rule_has_mitigation() -> None:
    # All shipped rules should propose a mitigation.
    for r in DEFAULT_RULES:
        assert r.suggested_mitigation, f"rule {r.rule_id} has no mitigation"


def test_every_default_rule_compiles(auditor: ClaimAuditor) -> None:
    # Compilation happened in __init__; if any pattern was broken, that
    # would have raised. This test just ensures the fixture builds.
    assert auditor.rules


# ---------- Positive matches per category ----------

@pytest.mark.parametrize(
    "text,expected_category",
    [
        ("Te aseguramos un resultado garantizado", ClaimCategory.GUARANTEED_OUTCOME),
        ("sin riesgo, te lo prometemos", ClaimCategory.RISK_FREE_CLAIM),
        ("Aumentá tus ingresos en 90 días", ClaimCategory.FINANCIAL_PROMISE),
        ("Ahorrá dinero con nuestra plataforma", ClaimCategory.FINANCIAL_PROMISE),
        ("ROI garantizado en cualquier escenario", ClaimCategory.FINANCIAL_PROMISE),
        ("Es deducible de impuestos", ClaimCategory.LEGAL_OR_TAX),
        ("Cura el insomnio en una semana", ClaimCategory.MEDICAL_OR_SENSITIVE),
        ("Somos los mejores del país", ClaimCategory.SUPERLATIVE),
        ("Líder absoluto del sector", ClaimCategory.SUPERLATIVE),
        ("Mejor que Notion para equipos chicos", ClaimCategory.COMPETITOR_COMPARISON),
        ("Más rápido que Salesforce", ClaimCategory.COMPETITOR_COMPARISON),
        ("Una solución increíble y revolucionaria", ClaimCategory.EXAGGERATED_BENEFIT),
        ("Vas a flipar con esto", ClaimCategory.EXAGGERATED_BENEFIT),
        ("Solo hoy: descuento especial", ClaimCategory.ARTIFICIAL_URGENCY),
        ("Últimas 5 unidades disponibles", ClaimCategory.ARTIFICIAL_URGENCY),
        ("Termina en 24 horas", ClaimCategory.ARTIFICIAL_URGENCY),
        ("Aumentá tus ventas en el primer mes", ClaimCategory.GENERIC_PROMISE),
        ("Siempre funciona, nunca falla", ClaimCategory.ABSOLUTE_CLAIM),
    ],
)
def test_rule_categories_fire_on_known_text(
    auditor: ClaimAuditor, text: str, expected_category: ClaimCategory
) -> None:
    detections = auditor.audit_text(text)
    cats = {d.category for d in detections}
    assert expected_category in cats, f"category {expected_category} not detected in: {text!r}"


# ---------- Severity escalation ----------

def test_unsafe_rules_produce_unsafe_severity(auditor: ClaimAuditor) -> None:
    detections = auditor.audit_text("Te aseguramos cura sin riesgo")
    severities = {d.severity for d in detections}
    assert ClaimSeverity.UNSAFE in severities


def test_caveat_only_for_mild_text(auditor: ClaimAuditor) -> None:
    detections = auditor.audit_text("Solo hoy hay descuento")
    severities = {d.severity for d in detections}
    # Should NOT be UNSAFE.
    assert ClaimSeverity.UNSAFE not in severities
    assert ClaimSeverity.CAVEAT in severities


# ---------- Clean text → no detections ----------

def test_clean_text_has_no_detections(auditor: ClaimAuditor) -> None:
    detections = auditor.audit_text(
        "Suite de automatización de marketing. Setup en menos de un día."
    )
    assert detections == []


def test_pluralization_not_overmatched(auditor: ClaimAuditor) -> None:
    # The word "tratamiento" should not trigger MEDICAL via "trata".
    detections = auditor.audit_text("Tratamiento de datos según GDPR")
    cats = {d.category for d in detections}
    assert ClaimCategory.MEDICAL_OR_SENSITIVE not in cats


# ---------- Custom rule sets ----------

def test_custom_rule_set_overrides_default() -> None:
    custom = (
        ClaimRule(
            rule_id="custom.banned",
            category=ClaimCategory.SUPERLATIVE,
            default_severity=ClaimSeverity.UNSAFE,
            description="custom",
            pattern=r"\bbanned-word\b",
        ),
    )
    auditor = ClaimAuditor(rules=custom, rule_set_id="custom.v1")
    assert auditor.rule_set_id == "custom.v1"
    assert len(auditor.rules) == 1
    detections = auditor.audit_text("This contains banned-word here")
    assert len(detections) == 1
    assert detections[0].rule_id == "custom.banned"
    # Default rules NOT loaded.
    none = auditor.audit_text("garantizado")
    assert none == []


def test_invalid_regex_raises_at_init() -> None:
    bad = (
        ClaimRule(
            rule_id="bad",
            category=ClaimCategory.SUPERLATIVE,
            default_severity=ClaimSeverity.CAVEAT,
            description="bad",
            pattern="(",
        ),
    )
    import re

    with pytest.raises(re.error):
        ClaimAuditor(rules=bad)


# ---------- Auditing the demo report ----------

@pytest.fixture
def demo_report(tmp_path: Path):
    mem = JsonFileMemory(tmp_path)
    pipeline = StrategyPipeline(memory=mem)
    return pipeline.run_from_path(DEMO_BRIEF).report


def test_demo_report_audit_produces_zero_or_some_detections(
    auditor: ClaimAuditor, demo_report
) -> None:
    # The deterministic templates produce conservative copy. The auditor
    # returns 0 detections on the bundled demo brief — which is the
    # expected baseline. This test pins that property.
    detections = auditor.audit(demo_report)
    assert detections == []


def test_audit_locates_in_returns_real_path(auditor: ClaimAuditor) -> None:
    """audit_text records the supplied path; audit walks structured fields."""
    detections = auditor.audit_text("garantizado", located_in="custom.path[0]")
    assert detections
    assert detections[0].located_in == "custom.path[0]"


# ---------- Hand-crafted report-shaped audit ----------

def test_audit_picks_up_risky_email_body(auditor: ClaimAuditor, demo_report) -> None:
    """Inject risky text into a report copy and confirm the walker finds it."""
    # Mutate the report's first email body with risky phrasing.
    modified = demo_report.model_copy(deep=True)
    modified.email_sequence.emails[0].body = (
        "Te aseguramos resultados garantizados, sin riesgo."
    )

    detections = auditor.audit(modified)
    assert any("email_sequence.emails[0].body" in d.located_in for d in detections)
    assert any(d.severity is ClaimSeverity.UNSAFE for d in detections)


def test_audit_picks_up_superlative_in_headline(
    auditor: ClaimAuditor, demo_report
) -> None:
    modified = demo_report.model_copy(deep=True)
    modified.value_proposition.headline = "Somos los mejores del mercado"

    detections = auditor.audit(modified)
    assert any(d.category is ClaimCategory.SUPERLATIVE for d in detections)
    assert any("value_proposition.headline" in d.located_in for d in detections)


def test_audit_demo_brief_round_trip_matches(auditor: ClaimAuditor) -> None:
    """Auditing the demo report twice yields equivalent results."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mem = JsonFileMemory(Path(tmp))
        pipeline = StrategyPipeline(memory=mem)
        report = pipeline.run_from_path(DEMO_BRIEF).report
        a = auditor.audit(report)
        b = auditor.audit(report)
        # Same rule_ids in same order.
        assert [d.rule_id for d in a] == [d.rule_id for d in b]


# ---------- Sanity ----------

def test_demo_brief_text_is_loadable() -> None:
    data = json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    assert data["client"]["slug"] == "demo-saas"
