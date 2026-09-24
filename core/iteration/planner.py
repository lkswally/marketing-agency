"""IterationPlanner — convert a CampaignFeedbackPack into the
next-cycle iteration plan (MKT-6C).

Pure planner. Same feedback pack → same iteration plan (modulo
fresh ids + timestamps). No HTTP, no LLM, no credential read,
no automatic mutation of any upstream pack.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from core.analytics import (
    OPTIMIZATION_RECOMMENDATION_PACK_KIND,
    OptimizationRecommendationPack,
)
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    MetricsSnapshot,
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
from core.feedback import (
    CAMPAIGN_FEEDBACK_PACK_KIND,
    CampaignFeedbackPack,
)
from core.feedback import SINGLETON_ID as FEEDBACK_SINGLETON
from core.feedback.models import (
    ChannelPriority,
    ContentSuggestionKind,
    SuggestedTaskPriority,
)
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
    NEXT_CAMPAIGN_ITERATION_PLAN_KIND,
    SINGLETON_ID,
    ABTestHypothesis,
    IterationAction,
    IterationActionKind,
    IterationActionPriority,
    IterationCalendarEntry,
    IterationExecutiveSummary,
    IterationStats,
    NewContentIdea,
    NewContentKind,
    NextCampaignIterationPlan,
    SuggestedIterationTask,
)

DEFAULT_ITERATION_PLANNER_RULE_SET_ID = "iteration-planner.v1"

# Sensible defaults for the suggested calendar.
_DEFAULT_NEXT_CYCLE_WEEKS = 4
_DEFAULT_FIRST_WEEK_OFFSET_DAYS = 7


# ---------- public API ----------


class IterationPlanner:
    """Build + persist a :class:`NextCampaignIterationPlan`."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def plan(self, client_slug: str) -> NextCampaignIterationPlan:
        feedback = self._load_required(
            client_slug, CAMPAIGN_FEEDBACK_PACK_KIND, FEEDBACK_SINGLETON,
            CampaignFeedbackPack,
            human="CampaignFeedbackPack",
            cli_hint="`mkt feedback-plan`",
        )
        rec_pack = self._try_load(
            client_slug, OPTIMIZATION_RECOMMENDATION_PACK_KIND,
            ANALYTICS_SINGLETON, OptimizationRecommendationPack,
        )
        # Snapshot is loaded best-effort but not currently used by the
        # planner (the feedback pack already carries the derived
        # email/social signals). Kept as a lookup so a future revision
        # that needs raw rows can use it without changing the signature.
        self._try_load(
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

        actions = self._build_actions(feedback)
        new_ideas = self._build_new_content_ideas(feedback, rec_pack)
        ab_tests = self._build_ab_test_hypotheses(feedback)
        calendar = self._build_calendar(actions, strategy)
        suggested_tasks = self._build_suggested_tasks(feedback)
        exec_summary = self._build_executive_summary(
            feedback=feedback,
            actions=actions,
            new_ideas=new_ideas,
            ab_tests=ab_tests,
        )

        stats = IterationStats(
            total_actions=len(actions),
            repeats=sum(1 for a in actions if a.kind is IterationActionKind.REPEAT_PIECE),
            pauses=sum(1 for a in actions if a.kind is IterationActionKind.PAUSE_PIECE),
            improves=sum(1 for a in actions if a.kind is IterationActionKind.IMPROVE_PIECE),
            creates=sum(1 for a in actions if a.kind is IterationActionKind.CREATE_NEW),
            channel_adjustments=sum(
                1 for a in actions
                if a.kind in (
                    IterationActionKind.CHANNEL_PROMOTE,
                    IterationActionKind.CHANNEL_PAUSE,
                )
            ),
            new_content_ideas=len(new_ideas),
            ab_test_hypotheses=len(ab_tests),
            calendar_entries=len(calendar),
            suggested_tasks=len(suggested_tasks),
        )

        return NextCampaignIterationPlan(
            client_slug=client_slug,
            feedback_pack_id=feedback.pack_id,
            feedback_pack_contract_version=feedback.contract_version,
            recommendation_pack_id=feedback.recommendation_pack_id,
            snapshot_id=feedback.snapshot_id,
            run_summary_id=getattr(run_summary, "run_id", None),
            task_pack_id=getattr(task_pack, "pack_id", None),
            creative_pack_id=getattr(creative, "pack_id", None),
            visual_pack_id=getattr(visual, "pack_id", None),
            strategy_report_id=getattr(strategy, "report_id", None),
            executive_summary=exec_summary,
            actions=actions,
            new_content_ideas=new_ideas,
            ab_test_hypotheses=ab_tests,
            calendar=calendar,
            suggested_tasks=suggested_tasks,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=DEFAULT_ITERATION_PLANNER_RULE_SET_ID,
        )

    def persist(self, plan: NextCampaignIterationPlan) -> None:
        self._memory.put(
            plan.client_slug,
            NEXT_CAMPAIGN_ITERATION_PLAN_KIND,
            SINGLETON_ID,
            plan.model_dump(mode="json"),
        )
        self._memory.append_audit_event_atomic(
            plan.client_slug,
            lambda prev_hash_arg: AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor="iteration_planner",
                occurred_at=utcnow(),
                client_slug=plan.client_slug,
                payload={
                    "next_campaign_iteration_plan": {
                        "plan_id": plan.plan_id,
                        "total_items": plan.total_items,
                        "total_actions": plan.stats.total_actions,
                        "new_content_ideas": plan.stats.new_content_ideas,
                        "ab_test_hypotheses": plan.stats.ab_test_hypotheses,
                        "action": "planned",
                    }
                },
                prev_hash=prev_hash_arg,
            ),
        )

    def load_latest(self, client_slug: str) -> NextCampaignIterationPlan:
        raw = self._memory.get(
            client_slug, NEXT_CAMPAIGN_ITERATION_PLAN_KIND, SINGLETON_ID
        )
        return NextCampaignIterationPlan.model_validate(raw)

    # ---------- internals ----------

    def _load_required(
        self, client_slug: str, kind: str, entity_id: str, cls,
        *, human: str, cli_hint: str,
    ):
        try:
            raw = self._memory.get(client_slug, kind, entity_id)
        except EntityNotFound as e:
            raise ValueError(
                f"no {human} for client {client_slug!r}; run "
                f"{cli_hint} first."
            ) from e
        return cls.model_validate(raw)

    def _try_load(self, client_slug: str, kind: str, entity_id: str, cls):
        try:
            raw = self._memory.get(client_slug, kind, entity_id)
        except EntityNotFound:
            return None
        return cls.model_validate(raw)

    # ---------- per-section builders ----------

    def _build_actions(
        self, feedback: CampaignFeedbackPack
    ) -> list[IterationAction]:
        out: list[IterationAction] = []
        # Content suggestions → REPEAT / IMPROVE / PAUSE actions.
        for cs in feedback.content_suggestions:
            if cs.kind is ContentSuggestionKind.REPEAT:
                kind = IterationActionKind.REPEAT_PIECE
            elif cs.kind is ContentSuggestionKind.IMPROVE:
                kind = IterationActionKind.IMPROVE_PIECE
            else:
                kind = IterationActionKind.PAUSE_PIECE
            out.append(
                IterationAction(
                    kind=kind,
                    priority=IterationActionPriority.HIGH
                    if cs.kind is ContentSuggestionKind.REPEAT
                    else IterationActionPriority.MEDIUM,
                    title=cs.title,
                    target_ref=cs.content_ref,
                    channel=cs.channel,
                    rationale=cs.rationale,
                    suggested_next_step=cs.suggested_next_step,
                    evidence_refs=list(cs.evidence_refs),
                )
            )
        # Channel adjustments → CHANNEL_PROMOTE / CHANNEL_PAUSE.
        for adj in feedback.channel_adjustments:
            if adj.new_priority is ChannelPriority.PAUSE:
                kind = IterationActionKind.CHANNEL_PAUSE
                priority = IterationActionPriority.MEDIUM
            elif adj.new_priority is ChannelPriority.HIGH:
                kind = IterationActionKind.CHANNEL_PROMOTE
                priority = IterationActionPriority.HIGH
            else:
                # Skip MEDIUM / LOW adjustments to keep the plan
                # focused. The feedback pack already lists them.
                continue
            out.append(
                IterationAction(
                    kind=kind,
                    priority=priority,
                    title=f"{kind.value.replace('_', ' ').title()}: {adj.channel}",
                    target_ref=None,
                    channel=adj.channel,
                    rationale=adj.rationale,
                    suggested_next_step=(
                        f"Aplicar prioridad `{adj.new_priority.value}` al canal "
                        f"`{adj.channel}` en el próximo brief."
                    ),
                    evidence_refs=list(adj.evidence_refs),
                )
            )
        return out

    def _build_new_content_ideas(
        self,
        feedback: CampaignFeedbackPack,
        rec_pack: OptimizationRecommendationPack | None,
    ) -> list[NewContentIdea]:
        out: list[NewContentIdea] = []
        # SEO recs → seo_article ideas.
        for rec in feedback.seo_recommendations[:5]:
            target_label = rec.query or rec.page or "(sin etiqueta)"
            out.append(
                NewContentIdea(
                    kind=NewContentKind.SEO_ARTICLE,
                    title=(
                        f"Nuevo artículo SEO atacando "
                        f"'{_truncate(target_label, 60)}'"
                    ),
                    channel="organic_search",
                    rationale=rec.rationale,
                    angle=(
                        "Cubrir intent + linking interno + meta optimization."
                    ),
                    target_audience=None,
                    priority=IterationActionPriority.HIGH
                    if rec.priority is SuggestedTaskPriority.HIGH
                    else IterationActionPriority.MEDIUM,
                    evidence_refs=list(rec.evidence_refs),
                )
            )
        # Best channel → suggest 1 new social_post variant.
        if rec_pack and rec_pack.best_channel:
            out.append(
                NewContentIdea(
                    kind=NewContentKind.SOCIAL_POST,
                    title=(
                        "Nueva pieza social aprovechando el winning "
                        f"channel ({rec_pack.best_channel})"
                    ),
                    channel=rec_pack.best_channel,
                    rationale=(
                        f"`{rec_pack.best_channel}` fue el canal con "
                        "mejor performance. Reforzar share con una pieza "
                        "alineada al ángulo que rindió."
                    ),
                    angle=(
                        "Adaptar el hook y formato de la pieza top performer."
                    ),
                    target_audience=None,
                    priority=IterationActionPriority.HIGH,
                    evidence_refs=[f"channel:{rec_pack.best_channel}"],
                )
            )
        # If we saw email recommendations → propose one new email
        # idea aligned to the rationale.
        for rec in feedback.email_recommendations[:2]:
            out.append(
                NewContentIdea(
                    kind=NewContentKind.EMAIL_DRAFT,
                    title=(
                        f"Email iterado sobre '{_truncate(rec.campaign_ref, 40)}'"
                    ),
                    channel="email",
                    rationale=rec.rationale,
                    angle=rec.suggested_action,
                    target_audience=None,
                    priority=_priority_from_feedback(rec.priority.value),
                    evidence_refs=list(rec.evidence_refs),
                )
            )
        return out

    def _build_ab_test_hypotheses(
        self, feedback: CampaignFeedbackPack
    ) -> list[ABTestHypothesis]:
        out: list[ABTestHypothesis] = []
        # Email recs → subject A/B test.
        for rec in feedback.email_recommendations[:2]:
            base = rec.campaign_ref or "email"
            out.append(
                ABTestHypothesis(
                    surface="email_subject",
                    variant_a=(
                        f"Subject actual (control) — basado en {base}"
                    ),
                    variant_b=(
                        "Subject reformulado: usar dato concreto + número"
                    ),
                    success_metric="open_rate",
                    success_threshold="uplift >= 20% sobre control",
                    rationale=rec.rationale,
                    evidence_refs=list(rec.evidence_refs),
                )
            )
        # Social recs → hook A/B test.
        for rec in feedback.social_recommendations[:2]:
            out.append(
                ABTestHypothesis(
                    surface="social_hook",
                    variant_a="Hook actual (control)",
                    variant_b=(
                        "Hook nuevo: pregunta directa al lector + claim "
                        "verificable"
                    ),
                    success_metric="engagement_rate",
                    success_threshold="uplift >= 30% sobre control",
                    rationale=rec.rationale,
                    evidence_refs=list(rec.evidence_refs),
                )
            )
        # If no email / social recs but we have channel adjustments,
        # propose a winning-channel format test.
        if not out and feedback.channel_adjustments:
            promotion = next(
                (
                    a for a in feedback.channel_adjustments
                    if a.new_priority is ChannelPriority.HIGH
                ),
                None,
            )
            if promotion:
                out.append(
                    ABTestHypothesis(
                        surface=f"{promotion.channel}_format",
                        variant_a="Formato actual (control)",
                        variant_b="Variante con carrousel / video corto",
                        success_metric="engagement_rate",
                        success_threshold="uplift >= 25% sobre control",
                        rationale=promotion.rationale,
                        evidence_refs=list(promotion.evidence_refs),
                    )
                )
        return out

    def _build_calendar(
        self,
        actions: list[IterationAction],
        strategy: CampaignStrategyReport | None,
    ) -> list[IterationCalendarEntry]:
        out: list[IterationCalendarEntry] = []
        weeks = (
            strategy.campaign_strategy.duration_weeks
            if strategy is not None
            else _DEFAULT_NEXT_CYCLE_WEEKS
        )
        weeks = max(2, min(int(weeks), 12))  # cap for sanity
        start_date = (
            utcnow().date()
            + timedelta(days=_DEFAULT_FIRST_WEEK_OFFSET_DAYS)
        )

        # Channel rotation seed: promotions first, then any channel
        # mentioned by an action.
        promotions = [
            a for a in actions
            if a.kind is IterationActionKind.CHANNEL_PROMOTE and a.channel
        ]
        pauses = {
            a.channel for a in actions
            if a.kind is IterationActionKind.CHANNEL_PAUSE and a.channel
        }
        rotation_channels: list[str] = []
        for a in promotions:
            if a.channel and a.channel not in rotation_channels:
                rotation_channels.append(a.channel)
        # Fallback to strategy-recommended channels if present.
        if not rotation_channels and strategy is not None:
            for ch in strategy.channel_recommendation.channels:
                if ch.channel_type.value in pauses:
                    continue
                rotation_channels.append(ch.channel_type.value)
        if not rotation_channels:
            rotation_channels = ["newsletter", "blog", "linkedin"]

        # Repeat / improve / create actions → first 1-2 weeks per
        # channel.
        action_pool: list[IterationAction] = [
            a for a in actions
            if a.kind in (
                IterationActionKind.REPEAT_PIECE,
                IterationActionKind.IMPROVE_PIECE,
                IterationActionKind.CREATE_NEW,
            )
        ]
        action_index = 0
        for week in range(1, weeks + 1):
            iso_date = start_date + timedelta(weeks=week - 1)
            channel = rotation_channels[(week - 1) % len(rotation_channels)]
            if channel in pauses:
                continue
            note = None
            action_ref = None
            if action_pool:
                a = action_pool[action_index % len(action_pool)]
                action_index += 1
                note = a.title[:200]
                action_ref = a.action_id
            out.append(
                IterationCalendarEntry(
                    week=week,
                    suggested_date=iso_date,
                    channel=channel,
                    piece_type=_default_piece_type_for(channel),
                    note=note,
                    action_ref=action_ref,
                )
            )
        return out

    def _build_suggested_tasks(
        self, feedback: CampaignFeedbackPack
    ) -> list[SuggestedIterationTask]:
        out: list[SuggestedIterationTask] = []
        # Promote the feedback pack's suggested_tasks into iteration
        # tasks, mapping priority + category strings.
        for t in feedback.suggested_tasks:
            out.append(
                SuggestedIterationTask(
                    title=t.title,
                    category=t.category.value,
                    priority=_priority_from_feedback(t.priority.value),
                    rationale=t.rationale,
                    suggested_owner=t.suggested_owner,
                    channel=t.channel,
                    evidence_refs=list(t.evidence_refs),
                )
            )
        # Append a measurement task to import the next cycle's data.
        out.append(
            SuggestedIterationTask(
                title="Importar métricas del próximo ciclo y re-correr análisis",
                category="measurement",
                priority=IterationActionPriority.MEDIUM,
                rationale=(
                    "Mantener el loop de feedback: importar las métricas "
                    "del próximo período, correr `mkt analyze-metrics` y "
                    "`mkt feedback-plan` antes del siguiente brief."
                ),
                suggested_owner="analytics_lead",
                evidence_refs=["pipeline:iteration-loop"],
            )
        )
        return out

    def _build_executive_summary(
        self,
        *,
        feedback: CampaignFeedbackPack,
        actions: list[IterationAction],
        new_ideas: list[NewContentIdea],
        ab_tests: list[ABTestHypothesis],
    ) -> IterationExecutiveSummary:
        bits: list[str] = []
        repeats = [a for a in actions if a.kind is IterationActionKind.REPEAT_PIECE]
        pauses = [a for a in actions if a.kind is IterationActionKind.PAUSE_PIECE]
        improves = [a for a in actions if a.kind is IterationActionKind.IMPROVE_PIECE]
        promos = [a for a in actions if a.kind is IterationActionKind.CHANNEL_PROMOTE]
        channel_pauses = [a for a in actions if a.kind is IterationActionKind.CHANNEL_PAUSE]
        if repeats:
            bits.append(
                f"Repetir {len(repeats)} pieza(s) que rindieron en el ciclo "
                "actual."
            )
        if improves:
            bits.append(
                f"Iterar {len(improves)} pieza(s) de performance media."
            )
        if pauses:
            bits.append(
                f"Pausar {len(pauses)} pieza(s) sin tracción."
            )
        if promos:
            bits.append(
                f"Subir prioridad de {len(promos)} canal/es."
            )
        if channel_pauses:
            bits.append(
                f"Pausar {len(channel_pauses)} canal/es al menos un ciclo."
            )
        if new_ideas:
            bits.append(
                f"Sumar {len(new_ideas)} idea(s) de contenido nueva(s)."
            )
        if ab_tests:
            bits.append(
                f"Correr {len(ab_tests)} test(s) A/B explícito(s) con "
                "criterio de éxito definido."
            )
        if not bits:
            bits.append(
                "Sin acciones fuertes para el próximo ciclo. Importar más "
                "métricas antes de iterar el brief."
            )
        return IterationExecutiveSummary(
            headline=(
                f"Plan de próxima iteración — {len(actions)} acciones, "
                f"{len(new_ideas)} ideas nuevas, {len(ab_tests)} tests A/B."
            ),
            paragraphs=bits,
            suggested_meeting_agenda=[
                "Aprobar acciones de repeat / improve / pause.",
                "Confirmar adjustes de canal (promote / pause).",
                "Priorizar las ideas de contenido nuevas.",
                "Definir owners + fechas para cada test A/B.",
                "Bloquear calendario del próximo ciclo en la herramienta de ops.",
            ],
        )


def plan_and_persist(memory: Memory, client_slug: str) -> NextCampaignIterationPlan:
    planner = IterationPlanner(memory=memory)
    plan = planner.plan(client_slug)
    planner.persist(plan)
    return plan


# ---------- helpers ----------


def _priority_from_feedback(value: str) -> IterationActionPriority:
    return {
        "high": IterationActionPriority.HIGH,
        "medium": IterationActionPriority.MEDIUM,
        "low": IterationActionPriority.LOW,
    }.get(value, IterationActionPriority.MEDIUM)


def _default_piece_type_for(channel: str) -> str:
    return {
        "newsletter": "email",
        "blog": "article",
        "linkedin": "post",
        "x": "thread",
        "instagram": "carousel",
        "tiktok": "reels_script",
        "email": "email",
        "organic_search": "article",
        "paid_search": "ad_copy",
    }.get(channel, "post")


def _truncate(text: Any, n: int) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


__all__ = [
    "DEFAULT_ITERATION_PLANNER_RULE_SET_ID",
    "IterationPlanner",
    "plan_and_persist",
]
