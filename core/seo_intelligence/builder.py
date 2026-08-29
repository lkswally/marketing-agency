"""SEOIntelligenceReportBuilder — deterministic consolidation (MKT-10C).

Reads, when available:

- :class:`~core.intake.models.ClientIntake` (kind=``client_intake``)
- :class:`~core.analytics.models.MetricsSnapshot` (kind=``metrics_snapshot``,
  period-scoped when a period is requested, else ``"current"``)
- an optional :class:`~core.seo_intelligence.models.SEOEvidenceInput`
  supplied by the CLI's ``--input`` flag

...and consolidates them into one :class:`SEOIntelligenceReportPack`.
**No scraping, no external API, no LLM.** Every finding traces back to one
of the three inputs above; anything not supplied is recorded as
:class:`MissingEvidence`, never fabricated.
"""

from __future__ import annotations

import hashlib
from datetime import date
from statistics import mean

from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)
from core.analytics.models import SINGLETON_ID as SNAPSHOT_SINGLETON_ID
from core.analytics.models import snapshot_entity_id as metrics_snapshot_entity_id
from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.intake import INTAKE_KIND
from core.intake import SINGLETON_ID as INTAKE_SINGLETON_ID
from core.intake.models import ClientIntake
from core.memory import EntityNotFound, Memory

from .models import (
    SEO_INTELLIGENCE_REPORT_PACK_KIND,
    SINGLETON_ID,
    ConfidenceLevel,
    FindingNature,
    KeywordCluster,
    MissingEvidence,
    SearchIntent,
    SEOEvidenceInput,
    SEOEvidenceSource,
    SEOExecutiveSummary,
    SEOFinding,
    SEOFindingCategory,
    SEOIntelligenceReportPack,
    SEOSeverity,
)

# Rule thresholds — module-level constants, same convention as
# core/ads_analysis/analyzer.py.
_LOW_ORGANIC_CTR = 0.02
_MIN_IMPRESSIONS_FOR_CTR_FINDING = 100.0
_LOW_AVG_POSITION_THRESHOLD = 20.0
_THIN_CONTENT_NOTE_TOKENS = ("thin content", "contenido pobre", "poco contenido")
_CANONICAL_NOTE_TOKENS = ("canonical",)
_INDEXATION_NOTE_TOKENS = ("noindex", "robots.txt", "sitemap", "indexation", "indexación")


def report_entity_id(client_slug: str, period_start: date, period_end: date) -> str:
    """Deterministic entity_id for a period-scoped report — mirrors
    :func:`core.analytics.models.snapshot_entity_id` (MKT-10B)."""
    key = f"{client_slug}-{period_start.isoformat()}-{period_end.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


class SEOIntelligenceReportBuilder:
    """Deterministic consolidator. No mutation of upstream packs."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # ---------- public API ----------

    def build(
        self,
        client_slug: str,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
        period_label: str | None = None,
        evidence_input: SEOEvidenceInput | None = None,
    ) -> SEOIntelligenceReportPack:
        intake = self._load_intake(client_slug)
        snapshot, snapshot_period_entity_id = self._load_snapshot(
            client_slug, period_start=period_start, period_end=period_end,
        )

        missing: list[MissingEvidence] = []
        ga4_rows = snapshot.rows_by_source(MetricSource.GA4) if snapshot else []
        gsc_rows = (
            snapshot.rows_by_source(MetricSource.SEARCH_CONSOLE) if snapshot else []
        )

        organic_findings = _organic_performance_findings(ga4_rows, gsc_rows, missing)
        page_arch_findings = _page_architecture_findings(evidence_input, missing)
        canonical_risks = _canonical_risks(evidence_input, missing)
        indexation_risks = _indexation_risks(evidence_input, missing)
        content_gaps = _content_gaps(evidence_input, missing)
        link_opportunities = _internal_link_opportunities(evidence_input)
        locale_opps = _locale_opportunities(evidence_input, intake, missing)
        competitor_findings = _competitor_findings(evidence_input, intake, missing)
        keyword_clusters = _keyword_clusters(evidence_input, missing)
        technical_findings = _technical_findings(evidence_input)

        if evidence_input is None:
            missing.append(MissingEvidence(
                category=SEOFindingCategory.EVIDENCE_STATUS,
                description=(
                    "No SEOEvidenceInput supplied — keyword research, "
                    "competitor notes, URL structure and technical notes "
                    "are all unavailable for this run. Pass --input <path>."
                ),
            ))
        if intake is None:
            missing.append(MissingEvidence(
                category=SEOFindingCategory.EVIDENCE_STATUS,
                description=(
                    f"No ClientIntake for {client_slug!r} — run "
                    "`mkt intake --file <path>` first for richer context."
                ),
            ))
        if snapshot is None:
            missing.append(MissingEvidence(
                category=SEOFindingCategory.EVIDENCE_STATUS,
                description=(
                    f"No MetricsSnapshot for {client_slug!r} — organic "
                    "performance is NOT_AVAILABLE. Run `mkt import-metrics` "
                    "or `mkt analytics-fetch --source ga4|search_console`."
                ),
            ))

        all_findings = (
            organic_findings + page_arch_findings + competitor_findings
        )
        roadmap, dev_gaps = _roadmap_and_dev_gaps(
            canonical_risks=canonical_risks,
            indexation_risks=indexation_risks,
            content_gaps=content_gaps,
            link_opportunities=link_opportunities,
        )
        exec_summary = _build_executive_summary(
            findings=all_findings,
            canonical_risks=canonical_risks,
            indexation_risks=indexation_risks,
            content_gaps=content_gaps,
            link_opportunities=link_opportunities,
            locale_opps=locale_opps,
            missing=missing,
        )
        next_decisions = _next_decisions(missing, roadmap)

        return SEOIntelligenceReportPack(
            client_slug=client_slug,
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            executive_summary=exec_summary,
            missing_evidence=missing,
            keyword_clusters=keyword_clusters,
            organic_performance_findings=organic_findings,
            page_architecture_findings=page_arch_findings,
            canonical_risks=canonical_risks,
            indexation_risks=indexation_risks,
            content_gaps=content_gaps,
            internal_link_opportunities=link_opportunities,
            locale_opportunities=locale_opps,
            competitor_findings=competitor_findings,
            technical_findings=technical_findings,
            roadmap=roadmap,
            development_gaps=dev_gaps,
            next_decisions_required=next_decisions,
            intake_id=intake.client_slug if intake else None,
            snapshot_id=snapshot.snapshot_id if snapshot else None,
            snapshot_period_entity_id=snapshot_period_entity_id,
            evidence_input_provided=evidence_input is not None,
            created_at=utcnow(),
        )

    def persist(self, pack: SEOIntelligenceReportPack) -> None:
        # Always write the 'current' singleton (backward compat, mirrors
        # MKT-10B's dual-write pattern).
        self._memory.put(
            pack.client_slug,
            SEO_INTELLIGENCE_REPORT_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        period_entity_id = None
        if pack.period_start is not None and pack.period_end is not None:
            period_entity_id = report_entity_id(
                pack.client_slug, pack.period_start, pack.period_end,
            )
            self._memory.put(
                pack.client_slug,
                SEO_INTELLIGENCE_REPORT_PACK_KIND,
                period_entity_id,
                pack.model_dump(mode="json"),
            )

        prev = self._memory.last_audit_hash(pack.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="seo_intelligence_builder",
            occurred_at=utcnow(),
            client_slug=pack.client_slug,
            payload={
                "seo_intelligence_report_pack": {
                    "action": "built",
                    "report_id": pack.report_id,
                    "period_start": str(pack.period_start) if pack.period_start else None,
                    "period_end": str(pack.period_end) if pack.period_end else None,
                    "period_entity_id": period_entity_id,
                    "missing_evidence_count": len(pack.missing_evidence),
                    "facts_count": pack.executive_summary.facts_count,
                    "hypotheses_count": pack.executive_summary.hypotheses_count,
                    "recommendations_count": pack.executive_summary.recommendations_count,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    # ---------- internals ----------

    def _load_intake(self, client_slug: str) -> ClientIntake | None:
        try:
            raw = self._memory.get(client_slug, INTAKE_KIND, INTAKE_SINGLETON_ID)
        except EntityNotFound:
            return None
        return ClientIntake.model_validate(raw)

    def _load_snapshot(
        self,
        client_slug: str,
        *,
        period_start: date | None,
        period_end: date | None,
    ) -> tuple[MetricsSnapshot | None, str | None]:
        if period_start is not None and period_end is not None:
            # Try every MetricSource that could carry the period key;
            # fall back to 'current' when none match.
            for source in (MetricSource.GA4, MetricSource.SEARCH_CONSOLE):
                entity_id = metrics_snapshot_entity_id(source, period_start, period_end)
                try:
                    raw = self._memory.get(client_slug, METRICS_SNAPSHOT_KIND, entity_id)
                    return MetricsSnapshot.model_validate(raw), entity_id
                except EntityNotFound:
                    continue
        try:
            raw = self._memory.get(
                client_slug, METRICS_SNAPSHOT_KIND, SNAPSHOT_SINGLETON_ID,
            )
        except EntityNotFound:
            return None, None
        return MetricsSnapshot.model_validate(raw), None


def build_and_persist(
    memory: Memory,
    *,
    client_slug: str,
    period_start: date | None = None,
    period_end: date | None = None,
    period_label: str | None = None,
    evidence_input: SEOEvidenceInput | None = None,
) -> SEOIntelligenceReportPack:
    """Run the builder + persist + audit in one call."""

    builder = SEOIntelligenceReportBuilder(memory=memory)
    pack = builder.build(
        client_slug,
        period_start=period_start,
        period_end=period_end,
        period_label=period_label,
        evidence_input=evidence_input,
    )
    builder.persist(pack)
    return pack


# ---------- section builders ----------


def _organic_performance_findings(
    ga4_rows: list[MetricRow],
    gsc_rows: list[MetricRow],
    missing: list[MissingEvidence],
) -> list[SEOFinding]:
    findings: list[SEOFinding] = []

    if not ga4_rows and not gsc_rows:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.ORGANIC_PERFORMANCE,
            description=(
                "No GA4 or Search Console rows in the snapshot — organic "
                "performance is NOT_AVAILABLE for this period."
            ),
        ))
        return findings

    if gsc_rows:
        impressions = sum(r.value for r in gsc_rows if r.metric_name == "impressions")
        clicks = sum(r.value for r in gsc_rows if r.metric_name == "clicks")
        positions = [
            r.value for r in gsc_rows if r.metric_name == "position" and r.value > 0
        ]
        if impressions >= _MIN_IMPRESSIONS_FOR_CTR_FINDING:
            ctr = (clicks / impressions) if impressions > 0 else 0.0
            if ctr < _LOW_ORGANIC_CTR:
                findings.append(SEOFinding(
                    category=SEOFindingCategory.ORGANIC_PERFORMANCE,
                    nature=FindingNature.FACT,
                    confidence=ConfidenceLevel.HIGH,
                    evidence_source=SEOEvidenceSource.SEARCH_CONSOLE,
                    severity=SEOSeverity.MEDIUM,
                    statement=(
                        f"Organic CTR is {ctr:.4f} over {impressions:.0f} "
                        "Search Console impressions — below the "
                        f"{_LOW_ORGANIC_CTR:.2%} reference threshold."
                    ),
                    evidence_refs=["search_console.impressions", "search_console.clicks"],
                    metrics_cited={"impressions": impressions, "clicks": clicks, "ctr": ctr},
                ))
                findings.append(SEOFinding(
                    category=SEOFindingCategory.ORGANIC_PERFORMANCE,
                    nature=FindingNature.HYPOTHESIS,
                    confidence=ConfidenceLevel.LOW,
                    evidence_source=SEOEvidenceSource.SEARCH_CONSOLE,
                    statement=(
                        "Low organic CTR at this impression volume MAY "
                        "indicate weak title tags / meta descriptions for "
                        "the ranking queries — NOT confirmed without a "
                        "SERP snippet audit."
                    ),
                    evidence_refs=["search_console.ctr"],
                ))
        if positions:
            avg_pos = mean(positions)
            if avg_pos > _LOW_AVG_POSITION_THRESHOLD:
                findings.append(SEOFinding(
                    category=SEOFindingCategory.ORGANIC_PERFORMANCE,
                    nature=FindingNature.FACT,
                    confidence=ConfidenceLevel.MEDIUM,
                    evidence_source=SEOEvidenceSource.SEARCH_CONSOLE,
                    severity=SEOSeverity.MEDIUM,
                    statement=(
                        f"Average Search Console position across "
                        f"{len(positions)} query rows is {avg_pos:.1f} — "
                        f"beyond the {_LOW_AVG_POSITION_THRESHOLD:.0f} "
                        "reference threshold for page-1/2 visibility."
                    ),
                    evidence_refs=["search_console.position"],
                    metrics_cited={"avg_position": avg_pos, "sample_rows": len(positions)},
                ))
    else:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.ORGANIC_PERFORMANCE,
            description=(
                "No Search Console rows in the snapshot — CTR / position "
                "facts are NOT_AVAILABLE. GA4-only data cannot substitute "
                "for query-level Search Console data."
            ),
        ))

    if ga4_rows:
        organic_sessions = sum(
            r.value for r in ga4_rows
            if r.metric_name == "sessions" and (r.channel or "").lower() in ("organic", "organic_search")
        )
        total_sessions = sum(r.value for r in ga4_rows if r.metric_name == "sessions")
        if total_sessions > 0:
            findings.append(SEOFinding(
                category=SEOFindingCategory.ORGANIC_PERFORMANCE,
                nature=FindingNature.FACT,
                confidence=ConfidenceLevel.HIGH,
                evidence_source=SEOEvidenceSource.GA4,
                statement=(
                    f"Organic sessions: {organic_sessions:.0f} of "
                    f"{total_sessions:.0f} total GA4 sessions in the "
                    "reported period."
                ),
                evidence_refs=["ga4.sessions"],
                metrics_cited={
                    "organic_sessions": organic_sessions,
                    "total_sessions": total_sessions,
                },
            ))
    else:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.ORGANIC_PERFORMANCE,
            description=(
                "No GA4 rows in the snapshot — organic session volume is "
                "NOT_AVAILABLE for this period."
            ),
        ))

    return findings


def _page_architecture_findings(
    evidence: SEOEvidenceInput | None,
    missing: list[MissingEvidence],
) -> list[SEOFinding]:
    if evidence is None or not evidence.url_structure:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.PAGE_ARCHITECTURE,
            description=(
                "No url_structure sample supplied in the evidence input — "
                "page architecture cannot be assessed."
            ),
        ))
        return []
    depths = [u.count("/") for u in evidence.url_structure]
    max_depth = max(depths) if depths else 0
    finding = SEOFinding(
        category=SEOFindingCategory.PAGE_ARCHITECTURE,
        nature=FindingNature.FACT,
        confidence=ConfidenceLevel.MEDIUM,
        evidence_source=SEOEvidenceSource.MANUAL_EVIDENCE,
        statement=(
            f"{len(evidence.url_structure)} representative URL paths "
            f"supplied; maximum path depth is {max_depth} segments."
        ),
        evidence_refs=list(evidence.url_structure[:10]),
    )
    return [finding]


def _canonical_risks(evidence: SEOEvidenceInput | None, missing: list[MissingEvidence]):
    if evidence is None or not evidence.technical_notes:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.CANONICALIZATION,
            description="No technical_notes supplied — canonicalization risk is NOT_AVAILABLE.",
        ))
        return []
    from .models import CanonicalRisk

    risks = []
    for note in evidence.technical_notes:
        if any(tok in note.lower() for tok in _CANONICAL_NOTE_TOKENS):
            risks.append(CanonicalRisk(
                description=note,
                severity=SEOSeverity.MEDIUM,
                nature=FindingNature.HYPOTHESIS,
            ))
    if not risks:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.CANONICALIZATION,
            description="Technical notes supplied but none mention canonical tags.",
        ))
    return risks


def _indexation_risks(evidence: SEOEvidenceInput | None, missing: list[MissingEvidence]):
    if evidence is None or not evidence.technical_notes:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.INDEXATION,
            description="No technical_notes supplied — indexation risk is NOT_AVAILABLE.",
        ))
        return []
    from .models import IndexationRisk

    risks = []
    for note in evidence.technical_notes:
        if any(tok in note.lower() for tok in _INDEXATION_NOTE_TOKENS):
            risks.append(IndexationRisk(
                description=note,
                severity=SEOSeverity.HIGH,
                nature=FindingNature.HYPOTHESIS,
            ))
    if not risks:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.INDEXATION,
            description="Technical notes supplied but none mention indexation signals.",
        ))
    return risks


def _content_gaps(evidence: SEOEvidenceInput | None, missing: list[MissingEvidence]):
    from .models import ContentGap

    gaps: list[ContentGap] = []
    if evidence is not None:
        for note in evidence.technical_notes:
            if any(tok in note.lower() for tok in _THIN_CONTENT_NOTE_TOKENS):
                gaps.append(ContentGap(
                    topic="(from technical note)",
                    kind="thin_content",
                    rationale=note,
                ))
    if not gaps:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.THIN_CONTENT,
            description=(
                "No thin-content signal in the supplied technical notes — "
                "thin content assessment is NOT_AVAILABLE."
            ),
        ))
    return gaps


def _internal_link_opportunities(evidence: SEOEvidenceInput | None):
    # Deterministic, conservative rule: with >= 2 URL paths supplied,
    # surface ONE structural opportunity — never a specific link guess
    # without more evidence than a bare path list.
    if evidence is None or len(evidence.url_structure) < 2:
        return []
    from .models import InternalLinkOpportunity

    paths = evidence.url_structure[:2]
    return [InternalLinkOpportunity(
        source_url=paths[0],
        target_url=paths[1],
        rationale=(
            "Both paths were supplied as representative URLs — review "
            "whether a contextual internal link between them exists. "
            "This is a structural suggestion, not a content-relevance "
            "match (no crawl / content analysis performed)."
        ),
    )]


def _locale_opportunities(
    evidence: SEOEvidenceInput | None,
    intake: ClientIntake | None,
    missing: list[MissingEvidence],
):
    from .models import LocaleOpportunity

    opps: list[LocaleOpportunity] = []
    if evidence is not None and evidence.locales:
        for loc in evidence.locales:
            opps.append(LocaleOpportunity(
                locale=loc.locale,
                description=loc.notes or f"Locale {loc.locale} supplied by operator.",
                is_active_today=loc.is_active,
                rationale=(
                    "Currently served." if loc.is_active
                    else "Target locale not yet served — evaluate expansion."
                ),
            ))
    elif intake is not None and intake.locale:
        opps.append(LocaleOpportunity(
            locale=intake.locale,
            description=f"Client intake declares locale {intake.locale!r}.",
            is_active_today=True,
            rationale="Sourced from ClientIntake.locale (single locale on file).",
        ))
    else:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.LOCALES,
            description="No locale data in the evidence input or client intake.",
        ))
    return opps


def _competitor_findings(
    evidence: SEOEvidenceInput | None,
    intake: ClientIntake | None,
    missing: list[MissingEvidence],
) -> list[SEOFinding]:
    competitors = []
    source = SEOEvidenceSource.MISSING
    if evidence is not None and evidence.competitors:
        competitors = evidence.competitors
        source = SEOEvidenceSource.MANUAL_EVIDENCE
    elif intake is not None and intake.known_competitors:
        competitors = intake.known_competitors
        source = SEOEvidenceSource.CLIENT_INTAKE

    if not competitors:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.COMPETITORS,
            description="No known competitors in the evidence input or client intake.",
        ))
        return []

    names = [c.name for c in competitors]
    return [SEOFinding(
        category=SEOFindingCategory.COMPETITORS,
        nature=FindingNature.FACT,
        confidence=ConfidenceLevel.MEDIUM,
        evidence_source=source,
        statement=(
            f"{len(competitors)} known competitor(s) on file: "
            f"{', '.join(names)}. No competitor SEO metrics were "
            "supplied — this is a roster fact, not a performance "
            "comparison."
        ),
        evidence_refs=names,
    )]


def _keyword_clusters(
    evidence: SEOEvidenceInput | None,
    missing: list[MissingEvidence],
) -> list[KeywordCluster]:
    if evidence is None or not evidence.keyword_research:
        missing.append(MissingEvidence(
            category=SEOFindingCategory.KEYWORD_RESEARCH,
            description=(
                "No keyword_research rows in the evidence input — keyword "
                "clusters and search-intent breakdown are NOT_AVAILABLE."
            ),
        ))
        return []

    by_intent: dict[SearchIntent, list] = {}
    for row in evidence.keyword_research:
        by_intent.setdefault(row.search_intent, []).append(row)

    clusters: list[KeywordCluster] = []
    for intent in sorted(by_intent, key=lambda i: i.value):
        rows = by_intent[intent]
        volumes = [r.search_volume for r in rows if r.search_volume is not None]
        positions = [r.current_position for r in rows if r.current_position is not None]
        clusters.append(KeywordCluster(
            label=f"{intent.value}_cluster",
            keywords=[r.keyword for r in rows],
            dominant_intent=intent,
            total_search_volume=sum(volumes) if volumes else None,
            avg_position=mean(positions) if positions else None,
        ))
    return clusters


def _technical_findings(evidence: SEOEvidenceInput | None) -> list:
    from .models import TechnicalSEOFinding

    if evidence is None or not evidence.technical_notes:
        return []
    findings = []
    for note in evidence.technical_notes:
        low = note.lower()
        if any(tok in low for tok in _CANONICAL_NOTE_TOKENS + _INDEXATION_NOTE_TOKENS + _THIN_CONTENT_NOTE_TOKENS):
            # Already surfaced as a more specific model above; skip here
            # to avoid duplicate reporting of the same note.
            continue
        findings.append(TechnicalSEOFinding(
            title="Operator-supplied technical note",
            description=note,
            severity=SEOSeverity.LOW,
            nature=FindingNature.HYPOTHESIS,
            source_note=note,
        ))
    return findings


def _roadmap_and_dev_gaps(
    *,
    canonical_risks: list,
    indexation_risks: list,
    content_gaps: list,
    link_opportunities: list,
):
    from .models import (
        AcceptanceCriterion,
        DevelopmentGap,
        RoadmapEffort,
        SEORoadmapPhase,
    )

    roadmap: list[SEORoadmapPhase] = []
    dev_gaps: list[DevelopmentGap] = []
    phase_num = 1

    if indexation_risks:
        roadmap.append(SEORoadmapPhase(
            phase_number=phase_num,
            title="Resolve indexation risks",
            objective="Confirm and fix indexation blockers surfaced by technical notes.",
            effort=RoadmapEffort.SMALL,
            related_finding_ids=[r.risk_id for r in indexation_risks],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="Each flagged URL/route returns 200 and is not blocked by robots.txt / noindex.",
                    metric_to_observe="indexed_pages_count",
                )
            ],
            can_become_task=True,
        ))
        dev_gaps.append(DevelopmentGap(
            title="Technical crawl to confirm indexation risks",
            description=(
                "Indexation risks below are HYPOTHESIS-nature — a real "
                "crawl or Search Console coverage report is needed to "
                "confirm before executing fixes."
            ),
            related_finding_ids=[r.risk_id for r in indexation_risks],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="Coverage report confirms/denies each flagged URL.",
                )
            ],
        ))
        phase_num += 1

    if canonical_risks:
        roadmap.append(SEORoadmapPhase(
            phase_number=phase_num,
            title="Audit canonical tags",
            objective="Verify canonical tag correctness on the flagged URLs.",
            effort=RoadmapEffort.SMALL,
            related_finding_ids=[r.risk_id for r in canonical_risks],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="Each flagged URL has a self-referencing or intentional canonical tag.",
                )
            ],
            can_become_task=True,
        ))
        phase_num += 1

    if content_gaps:
        roadmap.append(SEORoadmapPhase(
            phase_number=phase_num,
            title="Address content gaps",
            objective="Expand or rewrite pages flagged as thin / missing.",
            effort=RoadmapEffort.MEDIUM,
            related_finding_ids=[g.gap_id for g in content_gaps],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="Flagged pages reach the client's minimum content-quality bar.",
                    metric_to_observe="organic_sessions",
                )
            ],
            can_become_task=True,
        ))
        phase_num += 1

    if link_opportunities:
        roadmap.append(SEORoadmapPhase(
            phase_number=phase_num,
            title="Implement internal linking opportunities",
            objective="Add reviewed internal links between related pages.",
            effort=RoadmapEffort.SMALL,
            related_finding_ids=[o.opportunity_id for o in link_opportunities],
            acceptance_criteria=[
                AcceptanceCriterion(description="Links added and crawlable.")
            ],
            can_become_task=True,
        ))

    return roadmap, dev_gaps


def _build_executive_summary(
    *,
    findings: list[SEOFinding],
    canonical_risks: list,
    indexation_risks: list,
    content_gaps: list,
    link_opportunities: list,
    locale_opps: list,
    missing: list[MissingEvidence],
) -> SEOExecutiveSummary:
    facts = sum(1 for f in findings if f.nature == FindingNature.FACT)
    hyps = sum(1 for f in findings if f.nature == FindingNature.HYPOTHESIS)
    hyps += len(canonical_risks) + len(indexation_risks)
    recs = sum(1 for f in findings if f.nature == FindingNature.RECOMMENDATION)

    high_risk = sum(
        1 for r in (*canonical_risks, *indexation_risks)
        if r.severity == SEOSeverity.HIGH
    )

    top_opps: list[str] = []
    if link_opportunities:
        top_opps.append(f"{len(link_opportunities)} internal linking opportunity(ies)")
    if content_gaps:
        top_opps.append(f"{len(content_gaps)} content gap(s) to close")
    if locale_opps:
        inactive = [o for o in locale_opps if not o.is_active_today]
        if inactive:
            top_opps.append(f"{len(inactive)} locale expansion opportunity(ies)")
    top_opps = top_opps[:3]

    if not findings and not canonical_risks and not indexation_risks:
        headline = "Insufficient evidence to produce a substantive SEO diagnosis this period."
    else:
        headline = (
            f"{facts} confirmed fact(s), {hyps} hypothesis(es) and "
            f"{recs} recommendation(s) surfaced from available evidence."
        )

    coverage_note = (
        f"{len(missing)} evidence categor" +
        ("y" if len(missing) == 1 else "ies") +
        " missing this run; see 'Datos faltantes' for the full list."
        if missing else
        "All expected evidence categories had at least partial coverage."
    )

    return SEOExecutiveSummary(
        headline=headline,
        facts_count=facts,
        hypotheses_count=hyps,
        recommendations_count=recs,
        high_severity_risk_count=high_risk,
        top_opportunities=top_opps,
        evidence_coverage_note=coverage_note,
    )


def _next_decisions(missing: list[MissingEvidence], roadmap: list) -> list[str]:
    decisions: list[str] = []
    if missing:
        decisions.append(
            "Decide whether to supply the missing evidence categories "
            "before the next SEO report cycle, or proceed with partial "
            "coverage."
        )
    if roadmap:
        decisions.append(
            "Approve or reject the proposed roadmap phases before any "
            "are promoted into an execution task pack."
        )
    if not decisions:
        decisions.append(
            "No open decisions — re-run after the next reporting period "
            "to track delta."
        )
    return decisions


__all__ = [
    "SEOIntelligenceReportBuilder",
    "build_and_persist",
    "report_entity_id",
]
