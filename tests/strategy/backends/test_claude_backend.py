"""ClaudeStrategyBackend happy path with ScriptedClaudeInvoker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy import (
    BackendKind,
    CampaignStrategy,
    ClaudeStrategyBackend,
    EmailSequenceDraft,
    ScriptedClaudeInvoker,
    SocialPostDraft,
    StrategyInputBrief,
    TargetAudience,
    ValueProposition,
)
from core.strategy import templates as _t

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def brief() -> StrategyInputBrief:
    data = json.loads(DEMO_BRIEF.read_text(encoding="utf-8"))
    return StrategyInputBrief.model_validate(data)


@pytest.fixture
def audience(brief) -> TargetAudience:
    return _t.generate_target_audience(brief)


def _valid_vp_json() -> str:
    return json.dumps(
        {
            "headline": "Convertí a tus visitantes en clientes leales con automatización inteligente.",
            "category": "SaaS B2B",
            "target_audience_label": "Founders de SaaS late-seed",
            "differentiators": ["onboarding guiado", "métricas accionables"],
            "proof_points": ["pilotos con 12 clientes"],
            "primary_benefit": "menos churn",
            "notes": None,
        }
    )


def _valid_cs_json() -> str:
    return json.dumps(
        {
            "objective": "Reducir churn 15% en 8 semanas",
            "duration_weeks": 8,
            "primary_kpi": "Net revenue retention",
            "secondary_kpis": ["activation rate"],
            "funnel_focus": "retention",
            "budget_estimate": 5000.0,
            "budget_currency": "USD",
            "big_idea": "Onboarding como producto",
            "narrative_arc": ["semana 1: foco", "semana 4: validación"],
        }
    )


def test_kind_is_claude() -> None:
    backend = ClaudeStrategyBackend(invoker=ScriptedClaudeInvoker(responses={}))
    assert backend.kind is BackendKind.CLAUDE


def test_value_proposition_uses_invoker_output(brief, audience) -> None:
    inv = ScriptedClaudeInvoker(responses={"value_proposition": _valid_vp_json()})
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = backend.value_proposition(brief, audience)
    assert isinstance(vp, ValueProposition)
    assert "automatización" in vp.headline
    assert backend.drain_fallback_events() == []


def test_campaign_strategy_uses_invoker_output(brief, audience) -> None:
    inv = ScriptedClaudeInvoker(
        responses={
            "value_proposition": _valid_vp_json(),
            "campaign_strategy": _valid_cs_json(),
        }
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = backend.value_proposition(brief, audience)
    cs = backend.campaign_strategy(brief, vp)
    assert isinstance(cs, CampaignStrategy)
    assert cs.duration_weeks == 8
    assert backend.drain_fallback_events() == []


def test_social_drafts_requires_items_key(brief, audience) -> None:
    inv = ScriptedClaudeInvoker(
        responses={
            "social_post_drafts": json.dumps(
                {
                    "items": [
                        {
                            "post_id": "p1",
                            "channel": "instagram",
                            "hook": "Tu SaaS pierde usuarios silenciosamente.",
                            "body": "Te mostramos qué cambiar.",
                            "cta": "Agendá una demo",
                            "hashtags": ["#SaaS"],
                            "suggested_send_at": None,
                        }
                    ]
                }
            )
        }
    )
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = _t.generate_value_proposition(brief, audience)
    channels = _t.generate_channel_recommendation(brief, audience)
    kw = _t.generate_keyword_plan(brief, audience, vp)
    drafts = backend.social_post_drafts(brief, vp, channels, kw)
    assert len(drafts) == 1
    assert isinstance(drafts[0], SocialPostDraft)
    assert backend.drain_fallback_events() == []


def test_email_sequence_uses_invoker_output(brief, audience) -> None:
    payload = {
        "sequence_name": "Onboarding nurture",
        "goal": "Activación primer valor",
        "audience_label": "Trial users",
        "emails": [
            {
                "email_id": "e1",
                "step": 1,
                "subject": "Bienvenido a la herramienta",
                "preview_text": "Te llevamos a tu primer win en 3 pasos.",
                "body": "Hola, gracias por sumarte...",
                "cta": "Ir al setup",
                "send_after_days": 0,
            }
        ],
    }
    inv = ScriptedClaudeInvoker(responses={"email_sequence": json.dumps(payload)})
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = _t.generate_value_proposition(brief, audience)
    seq = backend.email_sequence(brief, vp, audience)
    assert isinstance(seq, EmailSequenceDraft)
    assert len(seq.emails) == 1


def test_handles_markdown_fenced_json(brief, audience) -> None:
    """Models often wrap JSON in ```json ... ``` despite being told not to."""
    fenced = "```json\n" + _valid_vp_json() + "\n```"
    inv = ScriptedClaudeInvoker(responses={"value_proposition": fenced})
    backend = ClaudeStrategyBackend(invoker=inv)
    vp = backend.value_proposition(brief, audience)
    assert isinstance(vp, ValueProposition)
    assert backend.drain_fallback_events() == []
