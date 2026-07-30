"""Pydantic models for the SEO Intelligence Report Pack (MKT-10C).

Contract: ``seo-intelligence-report.v1``.

Consolidates, when available, ``ClientIntake``, GA4 / Search Console rows
from ``MetricsSnapshot`` (manual imports or MKT-6D connectors), manually
supplied evidence (:class:`SEOEvidenceInput` — keyword research, known
competitors, URL structure, locales, technical notes) into one auditable
report.

**Cardinal rules** (mirrors the claim auditor / analytics analyzer posture):

- Never invent a metric. A finding with no underlying evidence is not
  emitted; the gap is recorded as :class:`MissingEvidence` instead.
- Every :class:`SEOFinding` declares its ``nature`` (fact vs hypothesis vs
  recommendation), a ``confidence`` level, and an ``evidence_source``. A
  finding whose evidence is absent uses
  ``evidence_source=SEOEvidenceSource.MISSING`` and
  ``confidence=ConfidenceLevel.NOT_AVAILABLE`` — it is never silently
  dropped when the *category itself* matters (e.g. "no keyword research
  supplied" is itself worth surfacing), but it is never asserted as fact.
- No scraping, no external API, no LLM. Purely deterministic consolidation
  + a small rule set over what was actually supplied.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug
from core.intake.models import CompetitorIntake

SEO_INTELLIGENCE_REPORT_PACK_VERSION = "seo-intelligence-report.v1"
SEO_INTELLIGENCE_REPORT_PACK_KIND = "seo_intelligence_report_pack"
SEO_EVIDENCE_INPUT_KIND = "seo_evidence_input"

SINGLETON_ID = "current"


# ============ Enums ============


class FindingNature(StrEnum):
    """Whether a finding is an observed fact, an inference, or advice."""

    FACT = "fact"
    """Directly backed by a metric row, intake field, or manual evidence."""

    HYPOTHESIS = "hypothesis"
    """A plausible explanation NOT directly confirmed by evidence —
    e.g. "low CTR is likely a title-tag issue" without a title-tag audit."""

    RECOMMENDATION = "recommendation"
    """An actionable next step. May reference a fact or a hypothesis."""


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_AVAILABLE = "not_available"
    """No usable evidence exists to assign a confidence level."""


class SEOEvidenceSource(StrEnum):
    """Where a finding's evidence came from."""

    GA4 = "ga4"
    SEARCH_CONSOLE = "search_console"
    METRICS_SNAPSHOT = "metrics_snapshot"
    """Generic snapshot source when the specific connector is not tagged."""
    CLIENT_INTAKE = "client_intake"
    MANUAL_EVIDENCE = "manual_evidence"
    """Operator-supplied :class:`SEOEvidenceInput`."""
    MISSING = "missing"
    """No evidence was supplied for this category."""


class SEOFindingCategory(StrEnum):
    """The 20 report categories the pack must distinguish (MKT-10C spec)."""

    EVIDENCE_STATUS = "evidence_status"
    KEYWORD_RESEARCH = "keyword_research"
    SEARCH_INTENT = "search_intent"
    ORGANIC_PERFORMANCE = "organic_performance"
    PAGE_ARCHITECTURE = "page_architecture"
    CANONICALIZATION = "canonicalization"
    INDEXATION = "indexation"
    THIN_CONTENT = "thin_content"
    INTERNAL_LINKING = "internal_linking"
    CONTENT_CLUSTERS = "content_clusters"
    LOCALES = "locales"
    COMPETITORS = "competitors"
    RISK = "risk"
    OPPORTUNITY = "opportunity"


class SEOSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SearchIntent(StrEnum):
    INFORMATIONAL = "informational"
    NAVIGATIONAL = "navigational"
    TRANSACTIONAL = "transactional"
    COMMERCIAL_INVESTIGATION = "commercial_investigation"
    UNKNOWN = "unknown"
    """Intent could not be determined from the supplied keyword data."""


class RoadmapEffort(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


# ============ Manual evidence input ============


class KeywordResearchRow(DomainModel):
    """One manually supplied or imported keyword research entry."""

    keyword: Annotated[str, Field(min_length=1, max_length=200)]
    search_intent: SearchIntent = SearchIntent.UNKNOWN
    search_volume: int | None = Field(default=None, ge=0)
    difficulty: float | None = Field(default=None, ge=0.0, le=100.0)
    current_position: float | None = Field(default=None, ge=0.0)
    target_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)


class LocaleInput(DomainModel):
    """One country / language target the client operates or wants to."""

    locale: Annotated[str, Field(min_length=2, max_length=10)]
    """BCP-47-ish tag, e.g. ``"es-AR"``, ``"en-US"``."""
    country: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    """Whether the client currently serves this locale (vs. a target)."""
    notes: str | None = Field(default=None, max_length=500)


class SEOEvidenceInput(DomainModel):
    """Operator-supplied evidence the CLI reads via ``--input``.

    Every field is optional — an absent field means "not supplied", not
    "empty/zero". The builder distinguishes the two: an empty list yields
    a :class:`MissingEvidence` entry, never a fabricated finding.
    """

    schema_version: Literal["seo-evidence-input.v1"] = "seo-evidence-input.v1"
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    keyword_research: list[KeywordResearchRow] = Field(default_factory=list)
    competitors: list[CompetitorIntake] = Field(default_factory=list)
    url_structure: list[str] = Field(default_factory=list)
    """Sample of representative URL paths, e.g. ``"/es/blog/<slug>"``."""
    locales: list[LocaleInput] = Field(default_factory=list)
    technical_notes: list[str] = Field(default_factory=list)
    """Free-form technical evidence supplied by the operator — e.g.
    "robots.txt blocks /search", "canonical tags missing on /blog/*"."""
    manual_seo_notes: str | None = Field(default=None, max_length=4000)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)


# ============ Findings ============


class SEOFinding(DomainModel):
    """One atomic observation, inference, or recommendation."""

    finding_id: str = Field(default_factory=new_id)
    category: SEOFindingCategory
    nature: FindingNature
    confidence: ConfidenceLevel
    evidence_source: SEOEvidenceSource
    severity: SEOSeverity | None = None
    """Only meaningful for risk-shaped findings; ``None`` for neutral facts."""
    statement: Annotated[str, Field(min_length=1, max_length=800)]
    evidence_refs: list[str] = Field(default_factory=list)
    """Free-form references — metric names, keyword strings, URL paths."""
    metrics_cited: dict[str, float] = Field(default_factory=dict)
    """Concrete numeric values backing a FACT-nature finding. Empty for
    hypotheses/recommendations that cite no metric directly."""


# ============ Structured sub-reports ============


class KeywordCluster(DomainModel):
    """A group of related keywords sharing a dominant search intent."""

    cluster_id: str = Field(default_factory=new_id)
    label: Annotated[str, Field(min_length=1, max_length=120)]
    keywords: list[str] = Field(default_factory=list)
    dominant_intent: SearchIntent = SearchIntent.UNKNOWN
    total_search_volume: int | None = Field(default=None, ge=0)
    """Sum of ``search_volume`` across member keywords. ``None`` when
    volume data was not supplied for any member."""
    avg_position: float | None = Field(default=None, ge=0.0)


class TechnicalSEOFinding(DomainModel):
    """A technical SEO observation NOT covered by the more specific
    canonicalization / indexation / thin-content models below."""

    finding_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=1, max_length=800)]
    severity: SEOSeverity
    nature: FindingNature
    source_note: str | None = Field(default=None, max_length=500)
    """The operator-supplied technical note this finding was derived
    from, verbatim, when applicable."""


class ContentGap(DomainModel):
    """A topic with search demand the client does not currently cover,
    OR a thin-content page flagged by the operator."""

    gap_id: str = Field(default_factory=new_id)
    topic: Annotated[str, Field(min_length=1, max_length=200)]
    related_keywords: list[str] = Field(default_factory=list)
    kind: Literal["missing_topic", "thin_content"] = "missing_topic"
    affected_url: str | None = Field(default=None, max_length=500)
    rationale: Annotated[str, Field(min_length=1, max_length=500)]


class InternalLinkOpportunity(DomainModel):
    """A suggested internal link between two URL paths."""

    opportunity_id: str = Field(default_factory=new_id)
    source_url: Annotated[str, Field(min_length=1, max_length=500)]
    target_url: Annotated[str, Field(min_length=1, max_length=500)]
    anchor_text_suggestion: str | None = Field(default=None, max_length=200)
    rationale: Annotated[str, Field(min_length=1, max_length=500)]


class CanonicalRisk(DomainModel):
    """A canonicalization risk surfaced from an operator technical note."""

    risk_id: str = Field(default_factory=new_id)
    affected_url: str | None = Field(default=None, max_length=500)
    description: Annotated[str, Field(min_length=1, max_length=800)]
    severity: SEOSeverity
    nature: FindingNature = FindingNature.HYPOTHESIS
    """Canonical risks are HYPOTHESIS by default unless the operator note
    explicitly confirms the behaviour (e.g. via a technical crawl)."""


class IndexationRisk(DomainModel):
    """An indexation risk (robots.txt, noindex, sitemap gaps, etc.)."""

    risk_id: str = Field(default_factory=new_id)
    affected_url: str | None = Field(default=None, max_length=500)
    description: Annotated[str, Field(min_length=1, max_length=800)]
    severity: SEOSeverity
    nature: FindingNature = FindingNature.HYPOTHESIS


class LocaleOpportunity(DomainModel):
    """A country / language opportunity or gap."""

    opportunity_id: str = Field(default_factory=new_id)
    locale: Annotated[str, Field(min_length=2, max_length=10)]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    is_active_today: bool
    rationale: Annotated[str, Field(min_length=1, max_length=500)]


# ============ Roadmap / dev handoff ============


class AcceptanceCriterion(DomainModel):
    """One testable condition that validates a roadmap phase / dev gap."""

    criterion_id: str = Field(default_factory=new_id)
    description: Annotated[str, Field(min_length=1, max_length=400)]
    metric_to_observe: str | None = Field(default=None, max_length=200)
    """The metric name a future period should check to validate this
    (feeds the future Learning Extractor / Decision Engine)."""


class DevelopmentGap(DomainModel):
    """A technical implementation gap that needs engineering work before
    an SEO recommendation can be executed."""

    gap_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=1, max_length=800)]
    related_finding_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)


class SEORoadmapPhase(DomainModel):
    """One phase of the SEO roadmap."""

    phase_id: str = Field(default_factory=new_id)
    phase_number: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    objective: Annotated[str, Field(min_length=1, max_length=500)]
    effort: RoadmapEffort
    related_finding_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    can_become_task: bool = False
    """Whether this phase is concrete enough to promote into a future
    ``CampaignExecutionTaskPack`` (mirrors the MKT-6H promoter pattern).
    Never auto-promoted here — advisory flag only."""


class MissingEvidence(DomainModel):
    """A category with no usable evidence — explicit, never inferred."""

    category: SEOFindingCategory
    description: Annotated[str, Field(min_length=1, max_length=400)]
    """What is missing and how to supply it, e.g. "No Search Console rows
    in the snapshot — run `mkt analytics-fetch --source search_console`"."""


# ============ Executive summary ============


class SEOExecutiveSummary(DomainModel):
    """Deterministic, templated executive summary — no LLM."""

    headline: Annotated[str, Field(min_length=1, max_length=300)]
    facts_count: int = Field(ge=0)
    hypotheses_count: int = Field(ge=0)
    recommendations_count: int = Field(ge=0)
    high_severity_risk_count: int = Field(ge=0)
    top_opportunities: list[str] = Field(default_factory=list)
    """Up to 3 short strings — highest-signal opportunities, if any."""
    evidence_coverage_note: Annotated[str, Field(min_length=1, max_length=500)]
    """One sentence summarising which evidence categories were and were
    not available for this run."""


# ============ Pack ============


class SEOIntelligenceReportPack(DomainModel):
    """Output of one ``mkt seo-report`` invocation.

    Persisted under kind=``seo_intelligence_report_pack``. Entity id is
    ``"current"`` (singleton, backward-compat) OR, when a period is
    supplied, a deterministic period-scoped id mirroring MKT-10B's
    ``snapshot_entity_id`` pattern (see
    :func:`core.seo_intelligence.builder.report_entity_id`).
    """

    contract_version: Literal["seo-intelligence-report.v1"] = (
        SEO_INTELLIGENCE_REPORT_PACK_VERSION
    )
    report_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    period_start: date | None = None
    period_end: date | None = None
    period_label: str | None = Field(default=None, max_length=64)

    # ---- 1. Executive summary ----
    executive_summary: SEOExecutiveSummary

    # ---- 2 / 19. Evidence status / missing data ----
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)

    # ---- 3-4. Keyword research + search intent ----
    keyword_clusters: list[KeywordCluster] = Field(default_factory=list)

    # ---- 5. Organic performance ----
    organic_performance_findings: list[SEOFinding] = Field(default_factory=list)

    # ---- 6. Page architecture ----
    page_architecture_findings: list[SEOFinding] = Field(default_factory=list)

    # ---- 7. Canonicalization ----
    canonical_risks: list[CanonicalRisk] = Field(default_factory=list)

    # ---- 8. Indexation ----
    indexation_risks: list[IndexationRisk] = Field(default_factory=list)

    # ---- 9-10-11. Thin content, internal linking, content clusters ----
    content_gaps: list[ContentGap] = Field(default_factory=list)
    internal_link_opportunities: list[InternalLinkOpportunity] = Field(
        default_factory=list
    )

    # ---- 12. Locales ----
    locale_opportunities: list[LocaleOpportunity] = Field(default_factory=list)

    # ---- 13. Competitors ----
    competitor_findings: list[SEOFinding] = Field(default_factory=list)

    # ---- 14-15. Risks / opportunities (cross-cutting rollups) ----
    technical_findings: list[TechnicalSEOFinding] = Field(default_factory=list)

    # ---- 16. Roadmap ----
    roadmap: list[SEORoadmapPhase] = Field(default_factory=list)

    # ---- 17-18. Dev gaps + acceptance criteria ----
    development_gaps: list[DevelopmentGap] = Field(default_factory=list)

    # ---- 20. Next decisions required ----
    next_decisions_required: list[str] = Field(default_factory=list)

    # ---- Provenance ----
    intake_id: str | None = None
    snapshot_id: str | None = None
    snapshot_period_entity_id: str | None = None
    evidence_input_provided: bool = False

    created_at: datetime
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC)")
        return v


__all__ = [
    "SEO_EVIDENCE_INPUT_KIND",
    "SEO_INTELLIGENCE_REPORT_PACK_KIND",
    "SEO_INTELLIGENCE_REPORT_PACK_VERSION",
    "SINGLETON_ID",
    "AcceptanceCriterion",
    "CanonicalRisk",
    "ConfidenceLevel",
    "ContentGap",
    "DevelopmentGap",
    "FindingNature",
    "IndexationRisk",
    "InternalLinkOpportunity",
    "KeywordCluster",
    "KeywordResearchRow",
    "LocaleInput",
    "LocaleOpportunity",
    "MissingEvidence",
    "RoadmapEffort",
    "SEOEvidenceInput",
    "SEOEvidenceSource",
    "SEOExecutiveSummary",
    "SEOFinding",
    "SEOFindingCategory",
    "SEOIntelligenceReportPack",
    "SEORoadmapPhase",
    "SEOSeverity",
    "SearchIntent",
    "TechnicalSEOFinding",
]
