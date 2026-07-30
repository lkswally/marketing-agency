"""SEO Intelligence Report Pack (MKT-10C).

Deterministic consolidation of ClientIntake + MetricsSnapshot (GA4 /
Search Console) + operator-supplied evidence into an auditable,
multi-tenant SEO diagnosis-and-roadmap report.

No scraping, no external API, no LLM, no site mutation, no publishing.
"""

from __future__ import annotations

from .builder import (
    SEOIntelligenceReportBuilder,
    build_and_persist,
    report_entity_id,
)
from .models import (
    SEO_EVIDENCE_INPUT_KIND,
    SEO_INTELLIGENCE_REPORT_PACK_KIND,
    SEO_INTELLIGENCE_REPORT_PACK_VERSION,
    SINGLETON_ID,
    AcceptanceCriterion,
    CanonicalRisk,
    ConfidenceLevel,
    ContentGap,
    DevelopmentGap,
    FindingNature,
    IndexationRisk,
    InternalLinkOpportunity,
    KeywordCluster,
    KeywordResearchRow,
    LocaleInput,
    LocaleOpportunity,
    MissingEvidence,
    RoadmapEffort,
    SearchIntent,
    SEOEvidenceInput,
    SEOEvidenceSource,
    SEOExecutiveSummary,
    SEOFinding,
    SEOFindingCategory,
    SEOIntelligenceReportPack,
    SEORoadmapPhase,
    SEOSeverity,
    TechnicalSEOFinding,
)
from .renderer import render_markdown_seo_report

__all__ = [
    "report_entity_id",
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
    "SEOIntelligenceReportBuilder",
    "SEOIntelligenceReportPack",
    "SEORoadmapPhase",
    "SEOSeverity",
    "SearchIntent",
    "TechnicalSEOFinding",
    "build_and_persist",
    "render_markdown_seo_report",
]
