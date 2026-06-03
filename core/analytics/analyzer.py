"""AnalyticsAnalyzer (MKT-6A) — turn a MetricsSnapshot into a
deterministic recommendation pack.

Pure function over the snapshot. Same rows → same recommendations
(modulo fresh ids and timestamps).

The heuristics intentionally stay simple and explicit. They are
the dumbest possible "useful" rules so the operator can audit
each recommendation against the underlying data:

- **Best channel** = channel with the highest total clicks +
  conversions (tied-broken by total impressions).
- **Worst channel** = channel with non-trivial impressions but
  zero or near-zero engagement / conversions.
- **Top content** = pieces with the highest total clicks +
  engagement.
- **SEO opportunity (low CTR)** = Search Console rows where
  ``impressions >= 100`` AND ``ctr <= 0.02``. Score =
  ``impressions * (0.05 - ctr)``.
- **SEO opportunity (low position)** = Search Console rows where
  ``impressions >= 100`` AND ``position > 10`` AND ``position <=
  30``. Score = ``impressions * 0.5``.
- **Pause** = channel/content with high impressions and zero
  clicks AND zero conversions.
- **Repeat** = single top performer (best channel + best content).
- **Improve** = mid-tier content (in top half but below the
  best) with a clear gap to the leader.

These rules NEVER call out to an LLM, NEVER make a network
request, NEVER read any env var.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory

from .models import (
    METRICS_SNAPSHOT_KIND,
    OPTIMIZATION_RECOMMENDATION_PACK_KIND,
    SINGLETON_ID,
    ChannelPerformanceSummary,
    ContentPerformanceSummary,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
    OptimizationRecommendationPack,
    Recommendation,
    RecommendationKind,
    RecommendationPriority,
    SEOOpportunity,
    SEOOpportunityReport,
)

DEFAULT_ANALYZER_RULE_SET_ID = "analytics-analyzer.v1"

# Heuristic thresholds — kept as constants so a future tuning
# block can revisit them in one place.
_SEO_MIN_IMPRESSIONS = 100.0
_SEO_LOW_CTR = 0.02
_SEO_TARGET_CTR = 0.05
_SEO_LOW_POSITION = 10.0
_SEO_HIGH_POSITION = 30.0
_PAUSE_MIN_IMPRESSIONS = 200.0


# ---------- public API ----------


class AnalyticsAnalyzer:
    """Build + persist an :class:`OptimizationRecommendationPack`."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def analyze(self, client_slug: str) -> OptimizationRecommendationPack:
        snapshot = self._load_snapshot(client_slug)
        channels = _channel_summaries(snapshot.rows)
        content = _content_summaries(snapshot.rows)
        seo = _seo_opportunities(snapshot.rows)
        best_channel = _pick_best_channel(channels)
        worst_channel = _pick_worst_channel(channels)
        recommendations = _build_recommendations(
            channels=channels,
            content=content,
            seo=seo,
            best_channel=best_channel,
            worst_channel=worst_channel,
        )
        next_actions = _build_next_actions(
            best_channel=best_channel,
            worst_channel=worst_channel,
            seo=seo,
            content=content,
        )
        return OptimizationRecommendationPack(
            client_slug=client_slug,
            snapshot_id=snapshot.snapshot_id,
            snapshot_contract_version=snapshot.contract_version,
            total_rows_analyzed=snapshot.total_rows,
            channels=channels,
            top_content=content[:10],
            seo_opportunities=seo,
            best_channel=best_channel,
            worst_channel=worst_channel,
            recommendations=recommendations,
            next_actions=next_actions,
            notes=(
                "Heurísticas deterministas; ningún LLM ni API externa "
                "fue consultado. Importar más datos refina los rankings."
                if snapshot.total_rows < 10
                else None
            ),
            created_at=utcnow(),
            rule_set_id=DEFAULT_ANALYZER_RULE_SET_ID,
        )

    def persist(self, pack: OptimizationRecommendationPack) -> None:
        self._memory.put(
            pack.client_slug,
            OPTIMIZATION_RECOMMENDATION_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        prev = self._memory.last_audit_hash(pack.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="analytics_analyzer",
            occurred_at=utcnow(),
            client_slug=pack.client_slug,
            payload={
                "analytics_analysis": {
                    "action": "analyzed",
                    "pack_id": pack.pack_id,
                    "snapshot_id": pack.snapshot_id,
                    "total_rows": pack.total_rows_analyzed,
                    "best_channel": pack.best_channel,
                    "worst_channel": pack.worst_channel,
                    "recommendations": len(pack.recommendations),
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    def load_latest(self, client_slug: str) -> OptimizationRecommendationPack:
        raw = self._memory.get(
            client_slug,
            OPTIMIZATION_RECOMMENDATION_PACK_KIND,
            SINGLETON_ID,
        )
        return OptimizationRecommendationPack.model_validate(raw)

    def _load_snapshot(self, client_slug: str) -> MetricsSnapshot:
        try:
            raw = self._memory.get(client_slug, METRICS_SNAPSHOT_KIND, SINGLETON_ID)
        except EntityNotFound as e:
            raise ValueError(
                f"no MetricsSnapshot for client {client_slug!r}; run "
                "`mkt import-metrics` at least once first."
            ) from e
        return MetricsSnapshot.model_validate(raw)


def analyze_and_persist(
    memory: Memory, client_slug: str
) -> OptimizationRecommendationPack:
    analyzer = AnalyticsAnalyzer(memory=memory)
    pack = analyzer.analyze(client_slug)
    analyzer.persist(pack)
    return pack


# ---------- channel summaries ----------


def _channel_summaries(rows: Iterable[MetricRow]) -> list[ChannelPerformanceSummary]:
    by_channel: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "clicks": 0.0,
            "impressions": 0.0,
            "engagement": 0.0,
            "conversions": 0.0,
            "ctr_sum": 0.0,
            "ctr_count": 0,
            "position_sum": 0.0,
            "position_count": 0,
            "sample_rows": 0,
        }
    )
    for r in rows:
        if not r.channel:
            continue
        bucket = by_channel[r.channel]
        bucket["sample_rows"] = int(bucket["sample_rows"]) + 1
        name = r.metric_name
        if name == "clicks":
            bucket["clicks"] += r.value
        elif name == "impressions":
            bucket["impressions"] += r.value
        elif name in ("engagement", "engagements", "opens"):
            bucket["engagement"] += r.value
        elif name in ("conversions",):
            bucket["conversions"] += r.value
        elif name == "ctr":
            bucket["ctr_sum"] += r.value
            bucket["ctr_count"] = int(bucket["ctr_count"]) + 1
        elif name == "position":
            bucket["position_sum"] += r.value
            bucket["position_count"] = int(bucket["position_count"]) + 1
        elif name in ("sessions", "users"):
            # Treat sessions / users as a proxy for engagement when
            # the source is GA4 (so newsletter clicks aren't unfairly
            # weighted higher than blog sessions).
            bucket["engagement"] += r.value
    out: list[ChannelPerformanceSummary] = []
    for channel, b in by_channel.items():
        ctr = (b["ctr_sum"] / b["ctr_count"]) if b["ctr_count"] else None
        position = (
            (b["position_sum"] / b["position_count"])
            if b["position_count"]
            else None
        )
        out.append(
            ChannelPerformanceSummary(
                channel=channel,
                total_clicks=b["clicks"],
                total_impressions=b["impressions"],
                total_engagement=b["engagement"],
                total_conversions=b["conversions"],
                avg_ctr=ctr,
                avg_position=position,
                sample_rows=int(b["sample_rows"]),
            )
        )
    # Sort by (clicks + conversions) desc, impressions desc as
    # tie-breaker.
    out.sort(
        key=lambda c: (-(c.total_clicks + c.total_conversions), -c.total_impressions)
    )
    return out


# ---------- content summaries ----------


def _content_summaries(
    rows: Iterable[MetricRow],
) -> list[ContentPerformanceSummary]:
    by_content: dict[str, dict[str, float | int | str | None]] = defaultdict(
        lambda: {
            "channel": None,
            "clicks": 0.0,
            "impressions": 0.0,
            "engagement": 0.0,
            "conversions": 0.0,
            "sample_rows": 0,
        }
    )
    for r in rows:
        if not r.content_ref:
            continue
        bucket = by_content[r.content_ref]
        bucket["sample_rows"] = int(bucket["sample_rows"]) + 1
        if bucket["channel"] is None and r.channel:
            bucket["channel"] = r.channel
        name = r.metric_name
        if name == "clicks":
            bucket["clicks"] += r.value
        elif name == "impressions":
            bucket["impressions"] += r.value
        elif name in ("engagement", "engagements", "opens"):
            bucket["engagement"] += r.value
        elif name in ("conversions",):
            bucket["conversions"] += r.value
        elif name in ("sessions", "users"):
            bucket["engagement"] += r.value
    out: list[ContentPerformanceSummary] = []
    for content_ref, b in by_content.items():
        out.append(
            ContentPerformanceSummary(
                content_ref=content_ref,
                channel=b["channel"],
                total_clicks=b["clicks"],
                total_impressions=b["impressions"],
                total_engagement=b["engagement"],
                total_conversions=b["conversions"],
                sample_rows=int(b["sample_rows"]),
            )
        )
    out.sort(
        key=lambda c: (
            -(c.total_clicks + c.total_engagement + c.total_conversions),
            -c.total_impressions,
        )
    )
    return out


# ---------- SEO opportunities ----------


def _seo_opportunities(rows: Iterable[MetricRow]) -> SEOOpportunityReport:
    # Pair (query, page) → metric_name → value.
    pairs: dict[tuple[str | None, str | None], dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r.source is not MetricSource.SEARCH_CONSOLE:
            continue
        key = (r.query, r.content_ref)
        pairs[key][r.metric_name] = r.value
    opps: list[SEOOpportunity] = []
    for (query, page), metrics in pairs.items():
        impressions = metrics.get("impressions", 0.0)
        clicks = metrics.get("clicks", 0.0)
        ctr = metrics.get("ctr")
        position = metrics.get("position")
        if impressions < _SEO_MIN_IMPRESSIONS:
            continue

        if ctr is not None and ctr <= _SEO_LOW_CTR:
            score = impressions * (_SEO_TARGET_CTR - ctr)
            if score > 0:
                opps.append(
                    SEOOpportunity(
                        query=query,
                        page=page,
                        impressions=impressions,
                        clicks=clicks,
                        ctr=ctr,
                        position=position,
                        opportunity_score=round(score, 2),
                        reason=(
                            f"CTR bajo ({ctr:.1%}) con muchas "
                            f"impresiones ({int(impressions)})."
                        ),
                    )
                )
                continue

        if (
            position is not None
            and _SEO_LOW_POSITION < position <= _SEO_HIGH_POSITION
        ):
            score = impressions * 0.5
            opps.append(
                SEOOpportunity(
                    query=query,
                    page=page,
                    impressions=impressions,
                    clicks=clicks,
                    ctr=ctr,
                    position=position,
                    opportunity_score=round(score, 2),
                    reason=(
                        f"Posición {position:.1f} con {int(impressions)} "
                        "impresiones — empuje a top 10 es alcanzable."
                    ),
                )
            )

    opps.sort(key=lambda o: -o.opportunity_score)
    notes = None
    if not opps:
        notes = (
            "Sin oportunidades de SEO detectadas con los datos importados. "
            "Importar más datos de Search Console o ajustar umbrales si "
            "los volúmenes son chicos."
        )
    return SEOOpportunityReport(opportunities=opps[:20], notes=notes)


# ---------- best/worst channel ----------


def _pick_best_channel(channels: list[ChannelPerformanceSummary]) -> str | None:
    if not channels:
        return None
    return channels[0].channel


def _pick_worst_channel(channels: list[ChannelPerformanceSummary]) -> str | None:
    """Worst = channel with non-trivial impressions but zero or
    near-zero clicks + conversions."""
    candidates = [
        c for c in channels
        if c.total_impressions >= _PAUSE_MIN_IMPRESSIONS
        and (c.total_clicks + c.total_conversions) <= 1.0
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda c: -c.total_impressions)
    return candidates[0].channel


# ---------- recommendations ----------


def _build_recommendations(
    *,
    channels: list[ChannelPerformanceSummary],
    content: list[ContentPerformanceSummary],
    seo: SEOOpportunityReport,
    best_channel: str | None,
    worst_channel: str | None,
) -> list[Recommendation]:
    out: list[Recommendation] = []

    # 1. Repeat best channel.
    if best_channel is not None and channels:
        top = channels[0]
        out.append(
            Recommendation(
                kind=RecommendationKind.REPEAT,
                priority=RecommendationPriority.HIGH,
                title=f"Repetir lo que funcionó en {best_channel}",
                rationale=(
                    f"{best_channel} acumuló {int(top.total_clicks)} clicks "
                    f"y {int(top.total_conversions)} conversions; es el "
                    "canal con mejor performance."
                ),
                suggested_action=(
                    f"Reservar el próximo ciclo a piezas similares a las "
                    f"que rindieron en {best_channel}."
                ),
                evidence_refs=[f"channel:{best_channel}"],
            )
        )

    # 2. Pause worst channel.
    if worst_channel is not None:
        worst = next(c for c in channels if c.channel == worst_channel)
        out.append(
            Recommendation(
                kind=RecommendationKind.PAUSE,
                priority=RecommendationPriority.MEDIUM,
                title=f"Pausar / repensar {worst_channel}",
                rationale=(
                    f"{worst_channel} acumuló {int(worst.total_impressions)} "
                    "impresiones pero casi cero clicks y conversiones. "
                    "Mantenerlo gasta tiempo del equipo."
                ),
                suggested_action=(
                    f"Pausar {worst_channel} 4 semanas o reformular su "
                    "ángulo antes de volver a publicar."
                ),
                evidence_refs=[f"channel:{worst_channel}"],
            )
        )

    # 3. Improve mid-tier content.
    if len(content) >= 2:
        leader = content[0]
        # Pick a mid-tier piece with non-trivial engagement but
        # well below the leader.
        candidates = [
            c for c in content[1:]
            if (c.total_clicks + c.total_engagement) > 0
            and (c.total_clicks + c.total_engagement)
            < 0.5 * (leader.total_clicks + leader.total_engagement)
        ]
        if candidates:
            target = candidates[0]
            out.append(
                Recommendation(
                    kind=RecommendationKind.IMPROVE,
                    priority=RecommendationPriority.MEDIUM,
                    title=(
                        f"Mejorar la pieza '{_truncate(target.content_ref, 60)}'"
                    ),
                    rationale=(
                        "Tiene engagement medio y queda muy debajo del top "
                        "performer; refinar copy/hook puede subirla."
                    ),
                    suggested_action=(
                        "Re-trabajar copy / thumbnail / CTA y re-promocionar."
                    ),
                    evidence_refs=[f"content:{target.content_ref}"],
                )
            )

    # 4. SEO opportunities — top 3 → high priority recommendations.
    for opp in seo.opportunities[:3]:
        target = opp.query or opp.page or "(sin etiqueta)"
        out.append(
            Recommendation(
                kind=RecommendationKind.SEO_OPPORTUNITY,
                priority=RecommendationPriority.HIGH
                if opp.opportunity_score >= 50
                else RecommendationPriority.MEDIUM,
                title=f"Optimizar SEO para '{_truncate(target, 60)}'",
                rationale=opp.reason,
                suggested_action=(
                    "Revisar meta title / description / encabezados y "
                    "links internos para subir CTR o posición."
                ),
                evidence_refs=[
                    f"seo:{opp.query or '?'}:{opp.page or '?'}",
                ],
            )
        )

    # 5. Generic next-action when there's nothing else.
    if not out:
        out.append(
            Recommendation(
                kind=RecommendationKind.NEXT_ACTION,
                priority=RecommendationPriority.LOW,
                title="Importar más datos antes de decidir",
                rationale=(
                    "El snapshot tiene pocos datos para diferenciar canales "
                    "o piezas. Sin más métricas, cualquier conclusión es "
                    "ruido."
                ),
                suggested_action=(
                    "Correr `mkt import-metrics` con CSV / JSON de al "
                    "menos 2 semanas de actividad por canal antes de "
                    "concluir."
                ),
                evidence_refs=[],
            )
        )

    return out


def _build_next_actions(
    *,
    best_channel: str | None,
    worst_channel: str | None,
    seo: SEOOpportunityReport,
    content: list[ContentPerformanceSummary],
) -> list[str]:
    out: list[str] = []
    if best_channel:
        out.append(
            f"Asignar mayor share de la próxima campaña a {best_channel}."
        )
    if worst_channel:
        out.append(
            f"Pausar {worst_channel} 4 semanas y revisar ángulo."
        )
    if seo.opportunities:
        out.append(
            f"Atacar las {len(seo.opportunities[:3])} oportunidades SEO de "
            "mayor score antes del próximo lanzamiento."
        )
    if content:
        leader = content[0]
        out.append(
            f"Documentar qué hizo distinto a la pieza top "
            f"('{_truncate(leader.content_ref, 60)}') y replicarlo."
        )
    if not out:
        out.append(
            "Importar más datos por canal antes de tomar decisiones de "
            "asignación."
        )
    return out


def _truncate(text: str | None, n: int) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


__all__ = [
    "AnalyticsAnalyzer",
    "DEFAULT_ANALYZER_RULE_SET_ID",
    "analyze_and_persist",
]
