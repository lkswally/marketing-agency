"""TemplatedStrategyBackend — campaign strategy engine backend.

When the dispatcher invokes an agent inside the W7 workflow, this backend
runs the appropriate deterministic generator from :mod:`core.strategy.templates`,
persists the produced entity into Memory, and returns a valid
:class:`ReturnEnvelope`.

For any other workflow, the backend transparently falls back to
:class:`MockAgentBackend` so it is safe to wire as the default backend in
any dispatcher.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from core.contracts import (
    ArtifactKind,
    ArtifactRef,
    EnvelopeStatus,
    ReturnEnvelope,
)
from core.domain.base import utcnow
from core.memory import Memory
from core.runtime.backend import AgentBackend, AgentInvocation
from core.runtime.backends.mock import MockAgentBackend

from . import templates
from .models import (
    CAMPAIGN_STRATEGY_VERSION,
    ApprovalChecklist,
    BusinessDiagnosis,
    BuyerPersona,
    CampaignSchedule,
    CampaignStrategy,
    CampaignStrategyReport,
    ChannelRecommendation,
    CompetitorBenchmark,
    CreativeBriefPack,
    EmailSequenceDraft,
    KeywordPlan,
    ReelsScriptPack,
    RiskAssessment,
    SocialPostDraft,
    StrategyInputBrief,
    SuggestedPiece,
    TargetAudience,
    ValueProposition,
)

STRATEGY_WORKFLOW_ID = "W7_campaign_strategy_engine"

# Memory kinds used by the strategy engine. Distinct from the runtime kinds
# the dispatcher already uses (envelope, workflow_run).
INPUT_BRIEF_KIND = "strategy_input_brief"
EXECUTIVE_SUMMARY_KIND = "strategy_executive_summary"
DIAGNOSIS_KIND = "strategy_diagnosis"
TARGET_AUDIENCE_KIND = "strategy_target_audience"
BUYER_PERSONA_KIND = "strategy_buyer_persona"
VALUE_PROPOSITION_KIND = "strategy_value_proposition"
COMPETITOR_BENCHMARK_KIND = "strategy_competitor_benchmark"
CHANNEL_RECOMMENDATION_KIND = "strategy_channel_recommendation"
KEYWORD_PLAN_KIND = "strategy_keyword_plan"
CAMPAIGN_STRATEGY_KIND = "strategy_campaign_strategy"
SUGGESTED_PIECES_KIND = "strategy_suggested_pieces"
CREATIVE_BRIEF_PACK_KIND = "strategy_creative_brief_pack"
SOCIAL_POSTS_KIND = "strategy_social_posts"
EMAIL_SEQUENCE_KIND = "strategy_email_sequence"
REELS_PACK_KIND = "strategy_reels_pack"
SCHEDULE_KIND = "strategy_schedule"
APPROVAL_CHECKLIST_KIND = "strategy_approval_checklist"
RISK_ASSESSMENT_KIND = "strategy_risk_assessment"
REPORT_KIND = "campaign_strategy_report"

# Stable id used as the entity id for the single brief / report per run.
# (Memory layer caps entity ids to a safe alphabet; "current" is short and
# obviously a singleton.)
SINGLETON_ID = "current"


class TemplatedStrategyBackend(AgentBackend):
    """Deterministic backend that drives the W7 campaign strategy workflow."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory
        self._fallback = MockAgentBackend()

    # ---------- AgentBackend ----------

    def run(self, invocation: AgentInvocation) -> ReturnEnvelope:
        if invocation.workflow_id != STRATEGY_WORKFLOW_ID:
            return self._fallback.run(invocation)

        handler = self._PHASE_HANDLERS.get(invocation.phase_id)
        if handler is None:
            return self._fallback.run(invocation)

        return handler(self, invocation)

    # ---------- internals ----------

    def _read_brief(self, client_slug: str) -> StrategyInputBrief:
        raw = self._memory.get(client_slug, INPUT_BRIEF_KIND, SINGLETON_ID)
        return StrategyInputBrief.model_validate(raw)

    def _put(self, client_slug: str, kind: str, entity_id: str, model) -> None:
        self._memory.put(client_slug, kind, entity_id, model.model_dump(mode="json"))

    def _envelope(
        self,
        invocation: AgentInvocation,
        kind: str,
        entity_id: str,
        notes: str | None = None,
    ) -> ReturnEnvelope:
        return ReturnEnvelope(
            status=EnvelopeStatus.COMPLETADO,
            agent=invocation.agent_id,
            task=f"[strategy] {invocation.workflow_id}.{invocation.phase_id}",
            client_slug=invocation.client_slug,
            artifacts=[
                ArtifactRef(
                    path=f"memory://{kind}/{entity_id}",
                    kind=ArtifactKind.MEMORY,
                    description=f"strategy artifact for phase {invocation.phase_id}",
                )
            ],
            memory_writes=[],
            bloqueadores=[],
            notes=notes
            or f"Templated output. workflow={invocation.workflow_id} phase={invocation.phase_id}.",
            produced_at=utcnow(),
        )

    # ---------- per-phase handlers ----------

    def _handle_intake(self, invocation: AgentInvocation) -> ReturnEnvelope:
        # The brief is loaded by the pipeline BEFORE the dispatcher runs.
        # This phase just confirms it is there (used to emit g_brief_captured).
        self._read_brief(invocation.client_slug)
        return self._envelope(
            invocation, INPUT_BRIEF_KIND, SINGLETON_ID, notes="brief intake verified"
        )

    def _handle_diagnose(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        diagnosis = templates.generate_diagnosis(brief)
        self._put(invocation.client_slug, DIAGNOSIS_KIND, SINGLETON_ID, diagnosis)
        return self._envelope(invocation, DIAGNOSIS_KIND, SINGLETON_ID)

    def _handle_audience(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        audience = templates.generate_target_audience(brief)
        persona = templates.generate_buyer_persona(audience, brief)
        self._put(invocation.client_slug, TARGET_AUDIENCE_KIND, SINGLETON_ID, audience)
        self._put(invocation.client_slug, BUYER_PERSONA_KIND, SINGLETON_ID, persona)
        return self._envelope(invocation, TARGET_AUDIENCE_KIND, SINGLETON_ID)

    def _handle_competitor(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        bench = templates.generate_competitor_benchmark(brief.competitors_known)
        self._put(invocation.client_slug, COMPETITOR_BENCHMARK_KIND, SINGLETON_ID, bench)
        return self._envelope(invocation, COMPETITOR_BENCHMARK_KIND, SINGLETON_ID)

    def _handle_positioning(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        audience_raw = self._memory.get(
            invocation.client_slug, TARGET_AUDIENCE_KIND, SINGLETON_ID
        )
        audience = TargetAudience.model_validate(audience_raw)
        value_prop = templates.generate_value_proposition(brief, audience)
        self._put(
            invocation.client_slug, VALUE_PROPOSITION_KIND, SINGLETON_ID, value_prop
        )
        return self._envelope(invocation, VALUE_PROPOSITION_KIND, SINGLETON_ID)

    def _handle_channels(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        audience = TargetAudience.model_validate(
            self._memory.get(invocation.client_slug, TARGET_AUDIENCE_KIND, SINGLETON_ID)
        )
        rec = templates.generate_channel_recommendation(brief, audience)
        self._put(invocation.client_slug, CHANNEL_RECOMMENDATION_KIND, SINGLETON_ID, rec)
        return self._envelope(invocation, CHANNEL_RECOMMENDATION_KIND, SINGLETON_ID)

    def _handle_keywords(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        audience = TargetAudience.model_validate(
            self._memory.get(invocation.client_slug, TARGET_AUDIENCE_KIND, SINGLETON_ID)
        )
        value_prop = ValueProposition.model_validate(
            self._memory.get(
                invocation.client_slug, VALUE_PROPOSITION_KIND, SINGLETON_ID
            )
        )
        kw = templates.generate_keyword_plan(brief, audience, value_prop)
        self._put(invocation.client_slug, KEYWORD_PLAN_KIND, SINGLETON_ID, kw)
        return self._envelope(invocation, KEYWORD_PLAN_KIND, SINGLETON_ID)

    def _handle_creative(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        audience = TargetAudience.model_validate(
            self._memory.get(invocation.client_slug, TARGET_AUDIENCE_KIND, SINGLETON_ID)
        )
        value_prop = ValueProposition.model_validate(
            self._memory.get(
                invocation.client_slug, VALUE_PROPOSITION_KIND, SINGLETON_ID
            )
        )
        channels = ChannelRecommendation.model_validate(
            self._memory.get(
                invocation.client_slug, CHANNEL_RECOMMENDATION_KIND, SINGLETON_ID
            )
        )
        keyword_plan = KeywordPlan.model_validate(
            self._memory.get(invocation.client_slug, KEYWORD_PLAN_KIND, SINGLETON_ID)
        )

        strategy = templates.generate_campaign_strategy(brief, value_prop)
        pieces = templates.generate_suggested_pieces(brief, channels)
        creative_pack = templates.generate_creative_brief_pack(
            brief, value_prop, audience
        )
        social_drafts = templates.generate_social_post_drafts(
            brief, value_prop, channels, keyword_plan
        )
        email_seq = templates.generate_email_sequence(brief, value_prop, audience)
        reels_pack = templates.generate_reels_script_pack(brief, value_prop, audience)

        self._put(
            invocation.client_slug, CAMPAIGN_STRATEGY_KIND, SINGLETON_ID, strategy
        )
        # Suggested pieces is a list — store as a wrapper.
        self._memory.put(
            invocation.client_slug,
            SUGGESTED_PIECES_KIND,
            SINGLETON_ID,
            {"items": [p.model_dump(mode="json") for p in pieces]},
        )
        self._put(
            invocation.client_slug, CREATIVE_BRIEF_PACK_KIND, SINGLETON_ID, creative_pack
        )
        self._memory.put(
            invocation.client_slug,
            SOCIAL_POSTS_KIND,
            SINGLETON_ID,
            {"items": [p.model_dump(mode="json") for p in social_drafts]},
        )
        self._put(invocation.client_slug, EMAIL_SEQUENCE_KIND, SINGLETON_ID, email_seq)
        self._put(invocation.client_slug, REELS_PACK_KIND, SINGLETON_ID, reels_pack)

        return self._envelope(invocation, CREATIVE_BRIEF_PACK_KIND, SINGLETON_ID)

    def _handle_calendar(self, invocation: AgentInvocation) -> ReturnEnvelope:
        brief = self._read_brief(invocation.client_slug)
        channels = ChannelRecommendation.model_validate(
            self._memory.get(
                invocation.client_slug, CHANNEL_RECOMMENDATION_KIND, SINGLETON_ID
            )
        )
        schedule = templates.generate_schedule(brief, channels)
        self._put(invocation.client_slug, SCHEDULE_KIND, SINGLETON_ID, schedule)
        return self._envelope(invocation, SCHEDULE_KIND, SINGLETON_ID)

    def _handle_report(self, invocation: AgentInvocation) -> ReturnEnvelope:
        client_slug = invocation.client_slug
        brief = self._read_brief(client_slug)

        # Read every persisted strategy artifact.
        report = CampaignStrategyReport(
            contract_version=CAMPAIGN_STRATEGY_VERSION,
            client_slug=client_slug,
            brief_id=str(brief.client.slug) + ":" + SINGLETON_ID,
            generated_at=utcnow(),
            executive_summary=templates.generate_executive_summary(brief),
            diagnosis=BusinessDiagnosis.model_validate(
                self._memory.get(client_slug, DIAGNOSIS_KIND, SINGLETON_ID)
            ),
            target_audience=TargetAudience.model_validate(
                self._memory.get(client_slug, TARGET_AUDIENCE_KIND, SINGLETON_ID)
            ),
            buyer_persona=BuyerPersona.model_validate(
                self._memory.get(client_slug, BUYER_PERSONA_KIND, SINGLETON_ID)
            ),
            value_proposition=ValueProposition.model_validate(
                self._memory.get(client_slug, VALUE_PROPOSITION_KIND, SINGLETON_ID)
            ),
            competitor_benchmark=CompetitorBenchmark.model_validate(
                self._memory.get(client_slug, COMPETITOR_BENCHMARK_KIND, SINGLETON_ID)
            ),
            channel_recommendation=ChannelRecommendation.model_validate(
                self._memory.get(
                    client_slug, CHANNEL_RECOMMENDATION_KIND, SINGLETON_ID
                )
            ),
            keyword_plan=KeywordPlan.model_validate(
                self._memory.get(client_slug, KEYWORD_PLAN_KIND, SINGLETON_ID)
            ),
            campaign_strategy=CampaignStrategy.model_validate(
                self._memory.get(client_slug, CAMPAIGN_STRATEGY_KIND, SINGLETON_ID)
            ),
            suggested_pieces=[
                SuggestedPiece.model_validate(p)
                for p in self._memory.get(client_slug, SUGGESTED_PIECES_KIND, SINGLETON_ID)["items"]
            ],
            creative_brief_pack=CreativeBriefPack.model_validate(
                self._memory.get(client_slug, CREATIVE_BRIEF_PACK_KIND, SINGLETON_ID)
            ),
            social_post_drafts=[
                SocialPostDraft.model_validate(p)
                for p in self._memory.get(client_slug, SOCIAL_POSTS_KIND, SINGLETON_ID)["items"]
            ],
            email_sequence=EmailSequenceDraft.model_validate(
                self._memory.get(client_slug, EMAIL_SEQUENCE_KIND, SINGLETON_ID)
            ),
            reels_script_pack=ReelsScriptPack.model_validate(
                self._memory.get(client_slug, REELS_PACK_KIND, SINGLETON_ID)
            ),
            schedule=CampaignSchedule.model_validate(
                self._memory.get(client_slug, SCHEDULE_KIND, SINGLETON_ID)
            ),
            approval_checklist=ApprovalChecklist(items=[]),  # filled in next phase
            risk_assessment=RiskAssessment(),  # filled in next phase
            next_steps=templates.generate_next_steps(),
        )

        # Persist the partial report; the approval phase will overwrite.
        self._put(client_slug, REPORT_KIND, SINGLETON_ID, report)
        return self._envelope(invocation, REPORT_KIND, SINGLETON_ID)

    def _handle_approval(self, invocation: AgentInvocation) -> ReturnEnvelope:
        client_slug = invocation.client_slug

        value_prop = ValueProposition.model_validate(
            self._memory.get(client_slug, VALUE_PROPOSITION_KIND, SINGLETON_ID)
        )
        bench = CompetitorBenchmark.model_validate(
            self._memory.get(client_slug, COMPETITOR_BENCHMARK_KIND, SINGLETON_ID)
        )

        checklist = templates.generate_approval_checklist()
        risks = templates.generate_risk_assessment(value_prop, bench)

        self._put(client_slug, APPROVAL_CHECKLIST_KIND, SINGLETON_ID, checklist)
        self._put(client_slug, RISK_ASSESSMENT_KIND, SINGLETON_ID, risks)

        # Re-fetch the partial report and update with checklist + risks.
        report_raw = self._memory.get(client_slug, REPORT_KIND, SINGLETON_ID)
        report_raw["approval_checklist"] = checklist.model_dump(mode="json")
        report_raw["risk_assessment"] = risks.model_dump(mode="json")
        self._memory.put(client_slug, REPORT_KIND, SINGLETON_ID, report_raw)

        return self._envelope(invocation, REPORT_KIND, SINGLETON_ID)

    # ---------- routing table ----------

    _PHASE_HANDLERS: ClassVar[dict[str, Callable]] = {
        "intake": _handle_intake,
        "diagnose": _handle_diagnose,
        "audience": _handle_audience,
        "competitor": _handle_competitor,
        "positioning": _handle_positioning,
        "channels": _handle_channels,
        "keywords": _handle_keywords,
        "creative": _handle_creative,
        "calendar": _handle_calendar,
        "report": _handle_report,
        "approval": _handle_approval,
    }


# Helper used by the CLI / pipeline to load + persist the input brief.

def persist_input_brief(
    memory: Memory, brief: StrategyInputBrief, *, _now: datetime | None = None
) -> str:
    """Persist a :class:`StrategyInputBrief` into Memory.

    Returns the brief reference id (composed slug:current).
    """
    memory.put(
        brief.client.slug,
        INPUT_BRIEF_KIND,
        SINGLETON_ID,
        brief.model_dump(mode="json"),
    )
    return f"{brief.client.slug}:{SINGLETON_ID}"


def load_input_brief_from_file(path) -> StrategyInputBrief:
    """Load a strategy input brief from a JSON file."""
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return StrategyInputBrief.model_validate(data)
