"""FeedbackPlanner — convert analytics recommendations into a
deliverable campaign feedback pack (MKT-6B).

Reads (best-effort) the persisted artifacts:

- ``OptimizationRecommendationPack`` (MKT-6A, REQUIRED)
- ``MetricsSnapshot`` (MKT-6A, optional but recommended)
- ``CampaignRunSummary`` (MKT-3F, optional)
- ``CampaignExecutionTaskPack`` (MKT-4E, optional)
- ``CreativeAssetPack`` (MKT-3C, optional)
- ``VisualDirectionPack`` (MKT-3D, optional)
- ``CampaignStrategyReport`` (MKT-3A, optional)

Pure planner. Same inputs → same pack (modulo fresh ids +
timestamps). No HTTP, no LLM, no credential read.
"""

from __future__ import annotations

from typing import Any

from core.analytics import (
    OPTIMIZATION_RECOMMENDATION_PACK_KIND,
    OptimizationRecommendationPack,
)
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    MetricSource,
    MetricsSnapshot,
    RecommendationKind,
)
from core.analytics.models import (
    SINGLETON_ID as ANALYTICS_SINGLETON,
)
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.domain.base import utcnow
from core.execution import EXECUTION_TASK_PACK_KIND, CampaignExecutionTaskPack
from core.execution import SINGLETON_ID as TASK_PACK_SINGLETON
from core.memory import EntityNotFound, Memory
from core.pipeline import (
    PIPELINE_RUN_KIND,
    PIPELINE_RUN_SINGLETON,
    CampaignRunSummary,
)
from core.strategy import (
    REPORT_KIND,
    CampaignStrategyReport,
)
from core.strategy import (
    SINGLETON_ID as STRATEGY_SINGLETON,
)
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

from .models import (
    CAMPAIGN_FEEDBACK_PACK_KIND,
    SINGLETON_ID,
    CampaignFeedbackPack,
    ChannelAdjustment,
    ChannelPriority,
    ContentSuggestion,
    ContentSuggestionKind,
    EmailRecommendation,
    ExecutiveSummary,
    FeedbackStats,
    SEORecommendation,
    SocialRecommendation,
    SuggestedTask,
    SuggestedTaskCategory,
    SuggestedTaskPriority,
)

DEFAULT_FEEDBACK_PLANNER_RULE_SET_ID = "campaign-feedback-planner.v1"

# Cutoffs for email + social recommendations.
_EMAIL_LOW_OPEN_RATE = 0.20
_EMAIL_LOW_CLICK_RATE = 0.02
_SOCIAL_LOW_ENGAGEMENT_PER_IMP = 0.01
_SOCIAL_MIN_IMPRESSIONS = 500.0


# ---------- public API ----------


class FeedbackPlanner:
    """Build + persist a :class:`CampaignFeedbackPack`."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def plan(self, client_slug: str) -> CampaignFeedbackPack:
        rec_pack = self._load_required(
            client_slug, OPTIMIZATION_RECOMMENDATION_PACK_KIND,
            ANALYTICS_SINGLETON, OptimizationRecommendationPack,
            human="OptimizationRecommendationPack",
            cli_hint="`mkt analyze-metrics`",
        )
        snapshot = self._try_load(
            client_slug, METRICS_SNAPSHOT_KIND, ANALYTICS_SINGLETON,
            MetricsSnapshot,
        )
        run_summary = self._try_load(
            client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON,
            CampaignRunSummary,
        )
        task_pack = self._try_load(
            client_slug, EXECUTION_TASK_PACK_KIND, TASK_PACK_SINGLETON,
            CampaignExecutionTaskPack,
        )
        creative = self._try_load(
            client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON,
            CreativeAssetPack,
        )
        visual = self._try_load(
            client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON,
            VisualDirectionPack,
        )
        strategy = self._try_load(
            client_slug, REPORT_KIND, STRATEGY_SINGLETON,
            CampaignStrategyReport,
        )

        # Build per-section content.
        suggested_tasks = self._build_tasks(rec_pack, strategy)
        channel_adjustments = self._build_channel_adjustments(rec_pack, strategy)
        content_suggestions = self._build_content_suggestions(
            rec_pack, creative
        )
        seo_recs = self._build_seo_recommendations(rec_pack)
        email_recs = self._build_email_recommendations(snapshot)
        social_recs = self._build_social_recommendations(snapshot)
        exec_summary = self._build_executive_summary(
            rec_pack, run_summary, snapshot,
        )

        stats = FeedbackStats(
            total_suggested_tasks=len(suggested_tasks),
            high_priority_tasks=sum(
                1 for t in suggested_tasks
                if t.priority is SuggestedTaskPriority.HIGH
            ),
            channel_adjustments=len(channel_adjustments),
            content_suggestions=len(content_suggestions),
            seo_recommendations=len(seo_recs),
            email_recommendations=len(email_recs),
            social_recommendations=len(social_recs),
        )

        return CampaignFeedbackPack(
            client_slug=client_slug,
            recommendation_pack_id=rec_pack.pack_id,
            recommendation_pack_contract_version=rec_pack.contract_version,
            snapshot_id=snapshot.snapshot_id if snapshot else None,
            run_summary_id=getattr(run_summary, "run_id", None),
            task_pack_id=getattr(task_pack, "pack_id", None),
            creative_pack_id=getattr(creative, "pack_id", None),
            visual_pack_id=getattr(visual, "pack_id", None),
            strategy_report_id=getattr(strategy, "report_id", None),
            executive_summary=exec_summary,
            suggested_tasks=suggested_tasks,
            channel_adjustments=channel_adjustments,
            content_suggestions=content_suggestions,
            seo_recommendations=seo_recs,
            email_recommendations=email_recs,
            social_recommendations=social_recs,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=DEFAULT_FEEDBACK_PLANNER_RULE_SET_ID,
        )

    def persist(self, pack: CampaignFeedbackPack) -> None:
        self._memory.put(
            pack.client_slug,
            CAMPAIGN_FEEDBACK_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        self._memory.append_audit_event_atomic(
            pack.client_slug,
            lambda prev_hash_arg: AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor="feedback_planner",
                occurred_at=utcnow(),
                client_slug=pack.client_slug,
                payload={
                    "campaign_feedback_pack": {
                        "pack_id": pack.pack_id,
                        "total_items": pack.total_items,
                        "high_priority_tasks": pack.stats.high_priority_tasks,
                        "channel_adjustments": pack.stats.channel_adjustments,
                        "action": "planned",
                    }
                },
                prev_hash=prev_hash_arg,
            ),
        )

    def load_latest(self, client_slug: str) -> CampaignFeedbackPack:
        raw = self._memory.get(client_slug, CAMPAIGN_FEEDBACK_PACK_KIND, SINGLETON_ID)
        return CampaignFeedbackPack.model_validate(raw)

    # ---------- internals ----------

    def _load_required(
        self, client_slug: str, kind: str, entity_id: str, cls,
        *, human: str, cli_hint: str,
    ):
        try:
            raw = self._memory.get(client_slug, kind, entity_id)
        except EntityNotFound as e:
            raise ValueError(
                f"no {human} for client {client_slug!r}; "
                f"run {cli_hint} first."
            ) from e
        return cls.model_validate(raw)

    def _try_load(self, client_slug: str, kind: str, entity_id: str, cls):
        try:
            raw = self._memory.get(client_slug, kind, entity_id)
        except EntityNotFound:
            return None
        return cls.model_validate(raw)

    # ---------- per-section builders ----------

    def _build_tasks(
        self,
        rec_pack: OptimizationRecommendationPack,
        strategy: CampaignStrategyReport | None,
    ) -> list[SuggestedTask]:
        out: list[SuggestedTask] = []
        # One SuggestedTask per analyzer recommendation.
        for r in rec_pack.recommendations:
            category, owner = self._category_for(r.kind)
            out.append(
                SuggestedTask(
                    title=r.title,
                    category=category,
                    priority=_priority_map(r.priority.value),
                    rationale=r.rationale,
                    suggested_owner=owner,
                    evidence_refs=[
                        f"recommendation:{r.recommendation_id}",
                        *r.evidence_refs,
                    ],
                )
            )
        # Add a measurement task to import next cycle's data.
        out.append(
            SuggestedTask(
                title="Importar métricas del próximo período",
                category=SuggestedTaskCategory.MEASUREMENT,
                priority=SuggestedTaskPriority.MEDIUM,
                rationale=(
                    "Para mantener el ciclo de feedback, importar las "
                    "métricas del próximo período (idealmente cada 2 "
                    "semanas) y volver a correr `mkt analyze-metrics`."
                ),
                suggested_owner="analytics_lead",
                evidence_refs=["pipeline:feedback-loop"],
            )
        )
        # Top SEO opp also gets a content task that's specifically
        # for the copywriter / SEO specialist team.
        for opp in rec_pack.seo_opportunities.opportunities[:2]:
            target = opp.query or opp.page or "(sin etiqueta)"
            out.append(
                SuggestedTask(
                    title=f"Re-trabajar copy para SEO: '{_truncate(target, 60)}'",
                    category=SuggestedTaskCategory.SEO,
                    priority=(
                        SuggestedTaskPriority.HIGH
                        if opp.opportunity_score >= 50
                        else SuggestedTaskPriority.MEDIUM
                    ),
                    rationale=opp.reason,
                    suggested_owner="seo_specialist",
                    evidence_refs=[
                        f"seo:{opp.query or '?'}:{opp.page or '?'}",
                    ],
                )
            )
        return out

    @staticmethod
    def _category_for(kind: RecommendationKind):
        if kind is RecommendationKind.REPEAT:
            return SuggestedTaskCategory.OPTIMIZATION, "account_lead"
        if kind is RecommendationKind.PAUSE:
            return SuggestedTaskCategory.OPTIMIZATION, "account_lead"
        if kind is RecommendationKind.IMPROVE:
            return SuggestedTaskCategory.CONTENT, "copywriter"
        if kind is RecommendationKind.SEO_OPPORTUNITY:
            return SuggestedTaskCategory.SEO, "seo_specialist"
        return SuggestedTaskCategory.OPERATIONAL, "account_lead"

    def _build_channel_adjustments(
        self,
        rec_pack: OptimizationRecommendationPack,
        strategy: CampaignStrategyReport | None,
    ) -> list[ChannelAdjustment]:
        out: list[ChannelAdjustment] = []
        current_by_channel: dict[str, ChannelPriority] = {}
        if strategy is not None:
            for ch in strategy.channel_recommendation.channels:
                # priority 1..5 in strategy → coarse high/med/low.
                if ch.priority <= 1:
                    p = ChannelPriority.HIGH
                elif ch.priority <= 3:
                    p = ChannelPriority.MEDIUM
                else:
                    p = ChannelPriority.LOW
                current_by_channel[ch.channel_type.value] = p

        # Promote the best channel.
        if rec_pack.best_channel:
            current = current_by_channel.get(rec_pack.best_channel)
            if current is not ChannelPriority.HIGH:
                out.append(
                    ChannelAdjustment(
                        channel=rec_pack.best_channel,
                        current_priority=current,
                        new_priority=ChannelPriority.HIGH,
                        rationale=(
                            f"`{rec_pack.best_channel}` fue el canal con "
                            "mejor performance en el período analizado. "
                            "Aumentar share del próximo ciclo."
                        ),
                        evidence_refs=[f"channel:{rec_pack.best_channel}"],
                    )
                )

        # Pause / demote the worst channel.
        if rec_pack.worst_channel:
            current = current_by_channel.get(rec_pack.worst_channel)
            out.append(
                ChannelAdjustment(
                    channel=rec_pack.worst_channel,
                    current_priority=current,
                    new_priority=ChannelPriority.PAUSE,
                    rationale=(
                        f"`{rec_pack.worst_channel}` acumuló muchas "
                        "impresiones con casi cero engagement. Pausar al "
                        "menos 4 semanas o reformular el ángulo."
                    ),
                    evidence_refs=[f"channel:{rec_pack.worst_channel}"],
                )
            )

        return out

    def _build_content_suggestions(
        self,
        rec_pack: OptimizationRecommendationPack,
        creative: CreativeAssetPack | None,
    ) -> list[ContentSuggestion]:
        out: list[ContentSuggestion] = []
        # Repeat the top content piece (if any).
        if rec_pack.top_content:
            top = rec_pack.top_content[0]
            out.append(
                ContentSuggestion(
                    kind=ContentSuggestionKind.REPEAT,
                    content_ref=top.content_ref,
                    channel=top.channel,
                    title=f"Repetir patrón de '{_truncate(top.content_ref, 60)}'",
                    rationale=(
                        f"Acumuló {int(top.total_clicks)} clicks y "
                        f"{int(top.total_engagement)} interacciones en "
                        "el período analizado — fue la pieza con mejor "
                        "performance."
                    ),
                    suggested_next_step=(
                        "Documentar qué hizo distinto a esta pieza "
                        "(hook, formato, timing) y replicarlo en el "
                        "próximo ciclo."
                    ),
                    evidence_refs=[f"content:{top.content_ref}"],
                )
            )
        # Improve mid-tier (second-best with clear gap).
        if len(rec_pack.top_content) >= 2:
            leader = rec_pack.top_content[0]
            for c in rec_pack.top_content[1:5]:
                gap = (leader.total_clicks + leader.total_engagement) - (
                    c.total_clicks + c.total_engagement
                )
                if gap > 0 and (c.total_clicks + c.total_engagement) > 0:
                    out.append(
                        ContentSuggestion(
                            kind=ContentSuggestionKind.IMPROVE,
                            content_ref=c.content_ref,
                            channel=c.channel,
                            title=(
                                f"Iterar copy / formato en "
                                f"'{_truncate(c.content_ref, 60)}'"
                            ),
                            rationale=(
                                "Engagement medio pero queda por debajo "
                                "del top performer."
                            ),
                            suggested_next_step=(
                                "Re-trabajar hook + CTA + thumbnail y "
                                "re-promocionar la pieza."
                            ),
                            evidence_refs=[f"content:{c.content_ref}"],
                        )
                    )
                    break
        # Pause low performer when blocked by analyzer worst_channel.
        if rec_pack.worst_channel and creative is not None:
            for post in creative.social_posts:
                if post.channel.value == rec_pack.worst_channel:
                    out.append(
                        ContentSuggestion(
                            kind=ContentSuggestionKind.PAUSE,
                            content_ref=post.asset_id,
                            channel=post.channel.value,
                            title=(
                                f"Pausar pieza en {post.channel.value}"
                            ),
                            rationale=(
                                f"El canal `{rec_pack.worst_channel}` "
                                "performa muy por debajo del promedio."
                            ),
                            suggested_next_step=(
                                "No publicar la pieza programada en este "
                                "canal hasta resolver el problema de fit."
                            ),
                            evidence_refs=[
                                f"channel:{rec_pack.worst_channel}",
                                f"asset:{post.asset_id}",
                            ],
                        )
                    )
                    break
        return out

    def _build_seo_recommendations(
        self, rec_pack: OptimizationRecommendationPack,
    ) -> list[SEORecommendation]:
        out: list[SEORecommendation] = []
        for opp in rec_pack.seo_opportunities.opportunities[:10]:
            high = opp.opportunity_score >= 50
            out.append(
                SEORecommendation(
                    query=opp.query,
                    page=opp.page,
                    priority=(
                        SuggestedTaskPriority.HIGH
                        if high
                        else SuggestedTaskPriority.MEDIUM
                    ),
                    suggested_action=(
                        "Revisar meta title / meta description / "
                        "encabezados / links internos."
                    ),
                    rationale=opp.reason,
                    opportunity_score=opp.opportunity_score,
                    evidence_refs=[
                        f"seo:{opp.query or '?'}:{opp.page or '?'}",
                    ],
                )
            )
        return out

    def _build_email_recommendations(
        self, snapshot: MetricsSnapshot | None,
    ) -> list[EmailRecommendation]:
        if snapshot is None:
            return []
        # Aggregate per campaign_id.
        by_campaign: dict[str, dict[str, float]] = {}
        for r in snapshot.rows:
            if r.source is not MetricSource.EMAIL or not r.content_ref:
                continue
            bucket = by_campaign.setdefault(r.content_ref, {})
            bucket[r.metric_name] = bucket.get(r.metric_name, 0.0) + r.value
        out: list[EmailRecommendation] = []
        for campaign_id, metrics in by_campaign.items():
            sent = metrics.get("sent", 0.0)
            opens = metrics.get("opens", 0.0)
            clicks = metrics.get("clicks", 0.0)
            open_rate = (opens / sent) if sent > 0 else None
            click_rate = (clicks / sent) if sent > 0 else None
            if open_rate is None and click_rate is None:
                continue
            if open_rate is not None and open_rate < _EMAIL_LOW_OPEN_RATE:
                out.append(
                    EmailRecommendation(
                        campaign_ref=campaign_id,
                        open_rate=open_rate,
                        click_rate=click_rate,
                        suggested_action=(
                            "Probar nuevo subject line + preview text. "
                            "A/B test sobre la próxima audiencia."
                        ),
                        rationale=(
                            f"Open rate {open_rate:.1%} por debajo del "
                            f"umbral {_EMAIL_LOW_OPEN_RATE:.0%}."
                        ),
                        priority=SuggestedTaskPriority.HIGH,
                        evidence_refs=[f"email:{campaign_id}"],
                    )
                )
            elif click_rate is not None and click_rate < _EMAIL_LOW_CLICK_RATE:
                out.append(
                    EmailRecommendation(
                        campaign_ref=campaign_id,
                        open_rate=open_rate,
                        click_rate=click_rate,
                        suggested_action=(
                            "Re-trabajar CTA y estructura del body. "
                            "Reducir distracciones, una sola CTA por email."
                        ),
                        rationale=(
                            f"Click rate {click_rate:.1%} por debajo del "
                            f"umbral {_EMAIL_LOW_CLICK_RATE:.0%}."
                        ),
                        priority=SuggestedTaskPriority.MEDIUM,
                        evidence_refs=[f"email:{campaign_id}"],
                    )
                )
        return out

    def _build_social_recommendations(
        self, snapshot: MetricsSnapshot | None,
    ) -> list[SocialRecommendation]:
        if snapshot is None:
            return []
        # Aggregate per (channel, content_ref).
        by_key: dict[tuple[str, str | None], dict[str, float]] = {}
        for r in snapshot.rows:
            if r.source is not MetricSource.SOCIAL or not r.channel:
                continue
            key = (r.channel, r.content_ref)
            bucket = by_key.setdefault(key, {})
            bucket[r.metric_name] = bucket.get(r.metric_name, 0.0) + r.value
        out: list[SocialRecommendation] = []
        for (channel, content_ref), metrics in by_key.items():
            impressions = metrics.get("impressions", 0.0)
            engagement = metrics.get("engagement", 0.0)
            if impressions < _SOCIAL_MIN_IMPRESSIONS:
                continue
            rate = engagement / impressions if impressions > 0 else 0.0
            if rate < _SOCIAL_LOW_ENGAGEMENT_PER_IMP:
                out.append(
                    SocialRecommendation(
                        channel=channel,
                        content_ref=content_ref,
                        suggested_action=(
                            "Reformular hook y primera línea visual. "
                            "Si el patrón se repite, revisar el ángulo "
                            "general del canal."
                        ),
                        rationale=(
                            f"Engagement ratio {rate:.2%} sobre "
                            f"{int(impressions)} impresiones — bajo "
                            f"del umbral {_SOCIAL_LOW_ENGAGEMENT_PER_IMP:.1%}."
                        ),
                        priority=SuggestedTaskPriority.MEDIUM,
                        evidence_refs=[
                            f"social:{channel}:{content_ref or '?'}",
                        ],
                    )
                )
        return out

    def _build_executive_summary(
        self,
        rec_pack: OptimizationRecommendationPack,
        run_summary: CampaignRunSummary | None,
        snapshot: MetricsSnapshot | None,
    ) -> ExecutiveSummary:
        bits: list[str] = []
        if rec_pack.best_channel:
            bits.append(
                f"`{rec_pack.best_channel}` rindió mejor que el resto "
                "de los canales en el período analizado."
            )
        if rec_pack.worst_channel:
            bits.append(
                f"`{rec_pack.worst_channel}` quedó muy por debajo y "
                "recomendamos pausarlo al menos un ciclo."
            )
        if rec_pack.seo_opportunities.opportunities:
            top_opp = rec_pack.seo_opportunities.opportunities[0]
            target = top_opp.query or top_opp.page or "(sin etiqueta)"
            bits.append(
                f"Hay {len(rec_pack.seo_opportunities.opportunities)} "
                "oportunidades de SEO accionables (la mayor: "
                f"`{_truncate(target, 60)}`)."
            )
        if not bits:
            bits.append(
                "Con los datos disponibles no hay conclusiones fuertes; "
                "importar más métricas antes de la próxima decisión."
            )
        rows_msg = (
            f"Análisis basado en {snapshot.total_rows} filas de métricas."
            if snapshot
            else "Análisis basado en recomendaciones del analyzer."
        )
        return ExecutiveSummary(
            headline=(
                f"Feedback de campaña — {len(rec_pack.recommendations)} "
                "recomendaciones para el próximo ciclo."
            ),
            paragraphs=[*bits, rows_msg],
            suggested_meeting_agenda=[
                "Revisar canal con mejor performance y plan para escalarlo.",
                "Decidir qué canal pausamos y por cuánto tiempo.",
                "Aprobar las 2-3 SEO opportunities prioritarias.",
                "Confirmar piezas a repetir / iterar / pausar.",
                "Definir cadencia de importación de métricas del próximo ciclo.",
            ],
        )


def plan_and_persist(memory: Memory, client_slug: str) -> CampaignFeedbackPack:
    planner = FeedbackPlanner(memory=memory)
    pack = planner.plan(client_slug)
    planner.persist(pack)
    return pack


# ---------- helpers ----------


def _priority_map(value: str) -> SuggestedTaskPriority:
    return {
        "high": SuggestedTaskPriority.HIGH,
        "medium": SuggestedTaskPriority.MEDIUM,
        "low": SuggestedTaskPriority.LOW,
    }.get(value, SuggestedTaskPriority.MEDIUM)


def _truncate(text: Any, n: int) -> str:
    text = text or ""
    text = str(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


__all__ = [
    "DEFAULT_FEEDBACK_PLANNER_RULE_SET_ID",
    "FeedbackPlanner",
    "plan_and_persist",
]
