"""Pydantic models for the campaign strategy engine.

Contract: ``campaign-strategy.v1``

These models are the structured outputs the strategy engine produces. They
are not part of the operational contract family in ``core.contracts/`` —
they are domain-specific artifacts of one workflow (W7). Same architectural
principle as the workflow spec living in ``core/workflows/`` (ADR 0006 D-6.1).

Every output is composable with the existing domain model (MKT-1B): the
report references the underlying ``MarketingBrief``, ``Client``, ``Brand``,
``Audience``, ``Competitor``, ``Offer`` entities by id.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug
from core.domain.enums import ChannelType

CAMPAIGN_STRATEGY_VERSION = "campaign-strategy.v1"


# ============ Section 1: Executive Summary ============

class ExecutiveSummary(DomainModel):
    headline: str = Field(min_length=1, max_length=400)
    one_liner: str = Field(min_length=1, max_length=280)
    primary_objective: str = Field(min_length=1)
    key_metrics: list[str] = Field(default_factory=list)


# ============ Section 2: Business Diagnosis ============

class BusinessDiagnosis(DomainModel):
    industry: str | None = None
    stage_observed: str  # e.g. "early traction", "scale-up", "established"
    strengths: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    assumptions_made: list[str] = Field(default_factory=list)


# ============ Section 3-4: Target Audience + Buyer Persona ============

class TargetAudience(DomainModel):
    audience_id: str
    label: str
    estimated_size_band: Literal["niche", "small", "medium", "large"] = "medium"
    demographics: dict[str, str] = Field(default_factory=dict)
    psychographics: dict[str, str] = Field(default_factory=dict)
    preferred_channels: list[ChannelType] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    desired_outcomes: list[str] = Field(default_factory=list)


class BuyerPersona(DomainModel):
    persona_id: str
    archetype_name: str
    age_range: str | None = None
    occupation: str | None = None
    a_day_in_life: str | None = None
    motivations: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)


# ============ Section 5: Value Proposition ============

class ValueProposition(DomainModel):
    headline: str = Field(min_length=1, max_length=280)
    category: str
    target_audience_label: str
    differentiators: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    primary_benefit: str | None = None
    notes: str | None = None


# ============ Section 6: Competitor Benchmark ============

class CompetitorEntry(DomainModel):
    competitor_id: str | None = None
    name: str
    url: str | None = None
    positioning_summary: str | None = None
    observed_strengths: list[str] = Field(default_factory=list)
    observed_weaknesses: list[str] = Field(default_factory=list)
    differentiating_angle_for_us: str | None = None


class CompetitorBenchmark(DomainModel):
    competitors: list[CompetitorEntry] = Field(default_factory=list)
    overall_takeaway: str | None = None
    market_gaps_identified: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


# ============ Section 7: Channel Recommendation ============

class ChannelEntry(DomainModel):
    channel_type: ChannelType
    label: str
    priority: int = Field(ge=1, le=5)  # 1 = highest
    rationale: str
    cadence_suggestion: str | None = None
    expected_role: str | None = None  # acquisition / engagement / nurture / conversion


class ChannelRecommendation(DomainModel):
    channels: list[ChannelEntry] = Field(default_factory=list)
    total_channels: int = Field(ge=0, le=10)
    rationale_overall: str | None = None
    out_of_scope_channels: list[ChannelType] = Field(default_factory=list)


# ============ Section 8-10: Keywords + Negatives + Hashtags ============

class KeywordCluster(DomainModel):
    label: str
    intent: Literal["informational", "navigational", "transactional", "comparative"]
    keywords: list[str] = Field(default_factory=list)
    suggested_match: Literal["broad", "phrase", "exact"] = "phrase"


class KeywordPlan(DomainModel):
    clusters: list[KeywordCluster] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    source: Literal["reasoning_only", "ga4", "ahrefs", "semrush"] = "reasoning_only"
    notes: str | None = None


# ============ Section 11: Campaign Strategy ============

class CampaignStrategy(DomainModel):
    objective: str
    duration_weeks: int = Field(ge=1, le=52)
    primary_kpi: str
    secondary_kpis: list[str] = Field(default_factory=list)
    funnel_focus: Literal["awareness", "consideration", "conversion", "retention", "full_funnel"] = "full_funnel"
    budget_estimate: float | None = Field(default=None, ge=0)
    budget_currency: str | None = None
    big_idea: str | None = None
    narrative_arc: list[str] = Field(default_factory=list)


# ============ Section 12: Suggested Pieces ============

class SuggestedPiece(DomainModel):
    piece_type: str  # e.g. "landing_page", "email_welcome", "instagram_carousel"
    channel: ChannelType
    purpose: str
    quantity: int = Field(default=1, ge=1)
    notes: str | None = None


# ============ Section 13: Creative Brief Pack ============

class CreativeBriefEntry(DomainModel):
    brief_id: str
    title: str
    piece_type: str  # e.g. "instagram_post", "linkedin_carousel", "hero_image"
    aspect_ratio: str  # "1:1", "9:16", "16:9", "4:5"
    visual_concept: str
    palette_hint: list[str] = Field(default_factory=list)
    typography_hint: str | None = None
    copy_overlay: list[str] = Field(default_factory=list)
    cta: str | None = None
    accessibility_notes: list[str] = Field(default_factory=list)
    prompt_for_image_model: str  # ready to paste into a future image-gen tool


class CreativeBriefPack(DomainModel):
    briefs: list[CreativeBriefEntry] = Field(default_factory=list)
    overall_visual_direction: str | None = None
    do_not_use: list[str] = Field(default_factory=list)


# ============ Section 14: Social Post Drafts ============

class SocialPostDraft(DomainModel):
    post_id: str
    channel: ChannelType
    hook: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    cta: str
    hashtags: list[str] = Field(default_factory=list)
    suggested_send_at: str | None = None  # ISO week-day-time, informational


# ============ Section 15: Email Sequence ============

class EmailDraft(DomainModel):
    email_id: str
    step: int = Field(ge=1)
    subject: str = Field(min_length=1, max_length=80)
    preview_text: str = Field(min_length=1, max_length=140)
    body: str = Field(min_length=1)
    cta: str
    send_after_days: int = Field(ge=0)


class EmailSequenceDraft(DomainModel):
    sequence_name: str
    goal: str
    audience_label: str
    emails: list[EmailDraft] = Field(default_factory=list)


# ============ Section 16: Reels Scripts ============

class ReelsScriptEntry(DomainModel):
    script_id: str
    title: str
    hook: str = Field(min_length=1, max_length=200)
    beats: list[str] = Field(default_factory=list)
    voiceover_lines: list[str] = Field(default_factory=list)
    on_screen_text: list[str] = Field(default_factory=list)
    cta: str
    target_duration_s: int = Field(ge=10, le=90)


class ReelsScriptPack(DomainModel):
    scripts: list[ReelsScriptEntry] = Field(default_factory=list)
    overall_tone: str | None = None


# ============ Section 17: Calendar / Schedule ============

class ScheduleEntry(DomainModel):
    week: int = Field(ge=1)
    channel: ChannelType
    piece_type: str
    cadence_note: str | None = None


class CampaignSchedule(DomainModel):
    weeks_total: int = Field(ge=1, le=52)
    start_date: date | None = None
    end_date: date | None = None
    entries: list[ScheduleEntry] = Field(default_factory=list)
    notes: str | None = None


# ============ Section 18: Approval Checklist ============

class ChecklistItem(DomainModel):
    item_id: str
    title: str
    severity: Literal["blocker", "must", "should"] = "must"
    category: str  # "strategy" / "creative" / "compliance" / "operational"
    notes: str | None = None


class ApprovalChecklist(DomainModel):
    items: list[ChecklistItem] = Field(default_factory=list)
    approvers_required: list[str] = Field(default_factory=list)


# ============ Section 19: Risk Assessment ============

class RiskItem(DomainModel):
    risk_id: str
    description: str
    severity: Literal["low", "medium", "high"] = "medium"
    mitigation: str | None = None
    claim_text: str | None = None  # if it's an unverified marketing claim


class RiskAssessment(DomainModel):
    risks: list[RiskItem] = Field(default_factory=list)
    unverified_claims_count: int = Field(default=0, ge=0)
    requires_compliance_audit: bool = False


# ============ TOP-LEVEL: CampaignStrategyReport ============

class CampaignStrategyReport(DomainModel):
    """The complete output of the campaign strategy engine for one client."""

    contract_version: Literal["campaign-strategy.v1"] = CAMPAIGN_STRATEGY_VERSION
    report_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    brief_id: str
    generated_at: datetime

    # 20 sections in numbered order (matches docs/runtime/campaign-strategy-engine.md):
    executive_summary: ExecutiveSummary                # 1
    diagnosis: BusinessDiagnosis                       # 2
    target_audience: TargetAudience                    # 3
    buyer_persona: BuyerPersona | None = None          # 4 (optional)
    value_proposition: ValueProposition                # 5
    competitor_benchmark: CompetitorBenchmark          # 6
    channel_recommendation: ChannelRecommendation     # 7
    keyword_plan: KeywordPlan                          # 8-10
    campaign_strategy: CampaignStrategy                # 11
    suggested_pieces: list[SuggestedPiece] = Field(default_factory=list)  # 12
    creative_brief_pack: CreativeBriefPack             # 13
    social_post_drafts: list[SocialPostDraft] = Field(default_factory=list)  # 14
    email_sequence: EmailSequenceDraft                 # 15
    reels_script_pack: ReelsScriptPack                 # 16
    schedule: CampaignSchedule                         # 17
    approval_checklist: ApprovalChecklist              # 18
    risk_assessment: RiskAssessment                    # 19
    next_steps: list[str] = Field(default_factory=list)  # 20

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("generated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware (UTC)")
        return v


# ============ Strategy Input Brief (the JSON file the user provides) ============

class _InputClient(DomainModel):
    slug: str
    name: str
    industry: str | None = None
    locale: str = "es-AR"

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)


class _InputBrand(DomainModel):
    name: str | None = None
    mission: str | None = None
    tone_words: list[str] = Field(default_factory=list)
    lexicon_do: list[str] = Field(default_factory=list)
    lexicon_dont: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    claim_style: str | None = None


class _InputProduct(DomainModel):
    name: str
    offer_type: Literal["product", "service", "subscription", "lead_magnet", "bundle", "other"] = "product"
    description: str | None = None
    value_props: list[str] = Field(default_factory=list)
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str | None = None


class _InputAudienceHint(DomainModel):
    label: str
    description: str | None = None
    demographics: dict[str, str] = Field(default_factory=dict)
    psychographics: dict[str, str] = Field(default_factory=dict)
    preferred_channels: list[ChannelType] = Field(default_factory=list)
    estimated_size: int | None = Field(default=None, ge=0)


class _InputCompetitor(DomainModel):
    name: str
    url: str | None = None
    positioning_summary: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class StrategyInputBrief(DomainModel):
    """The JSON file the user provides as input to `mkt run-strategy`."""

    schema_version: Literal["strategy-input-brief.v1"] = "strategy-input-brief.v1"
    client: _InputClient
    brand: _InputBrand = Field(default_factory=_InputBrand)
    product: _InputProduct
    objective: str = Field(min_length=1)
    audience_hints: list[_InputAudienceHint] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    preferred_channels: list[ChannelType] = Field(default_factory=list)
    competitors_known: list[_InputCompetitor] = Field(default_factory=list)
    budget_amount: float | None = Field(default=None, ge=0)
    budget_currency: str | None = None
    deadline: date | None = None
    duration_weeks: int = Field(default=8, ge=1, le=52)
    primary_kpi: str = "qualified_leads"
    additional_context: str | None = None
