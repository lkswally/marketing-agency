"""TaskFactory — builds a CampaignExecutionTaskPack from upstream packs.

Pure function over the input packs. Same inputs → same task pack
(modulo fresh ids and the ``created_at`` / ``updated_at`` timestamps
the factory injects).

Task generation rules — applied in this order:

1. **Approval-driven tasks**. One task per checklist item; one per
   unverified claim; one per risk item with severity blocker/high.
2. **Channel-bound tasks**. For each channel in the recommendation:
   one setup task, one cadence-confirmation task.
3. **Per-creative-asset tasks**. For each social post, email,
   reels script, flyer copy, image prompt: one QA task plus one
   publish task. Image prompts also get a render task.
4. **SEO/GEO tasks**. UTM scheme, alt text, schema markup; one task
   per blog/article piece in the schedule.
5. **Email marketing tasks**. ESP setup, sequence configuration,
   per-step preview.
6. **Social marketing tasks**. Handle confirmation, scheduling-tool
   setup, hashtag review.
7. **Design tasks**. Visual direction approval, per-prompt brief
   review, per-prompt manual render.
8. **Measurement tasks**. UTM convention, tracking-event spec, KPI
   dashboard (planned, NOT connected to GA4 / Ads).
9. **Calendar tasks**. One task per week in the schedule that says
   "review week N pieces" — gives the operator a checkpoint.

Blocking rules:
- If ApprovalPack.blocks_publish is True OR any
  CreativeAssetState is BLOCKED, every PUBLISHING-category task is
  emitted in state BLOCKED with an explicit blocked_reason.
- If a task depends_on a blocked task, the dependent is BLOCKED too.

Priority rules:
- HIGH: tasks that gate the campaign launch (approval items with
  severity=blocker, claim review, blocked-asset resolution).
- MEDIUM: per-channel setup, per-piece QA, measurement spec.
- LOW: calendar checkpoints, polish.

No external services. No network. No publishing. No email send. No
image generation. Output is data only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from core.approval.models import ApprovalPack
from core.creative.models import CreativeAssetPack, CreativeAssetState
from core.domain.base import utcnow
from core.memory import Memory
from core.strategy.models import CampaignStrategyReport
from core.visual.models import VisualDirectionPack

from .models import (
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
)

EXECUTION_TASK_PACK_KIND = "campaign_execution_task_pack"
SINGLETON_ID = "current"
DEFAULT_TASK_RULE_SET_ID = "execution-task-default.v1"


# Severity strings the ApprovalPack uses. Kept as local constants so
# the dependency surface against ApprovalPack stays small.
_BLOCKER_SEVERITIES = {"blocker", "high"}


# ---------- public API ----------


class TaskFactory:
    """Build + persist a :class:`CampaignExecutionTaskPack`."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def build(
        self,
        report: CampaignStrategyReport,
        approval: ApprovalPack | None,
        creative: CreativeAssetPack | None,
        visual: VisualDirectionPack | None,
    ) -> CampaignExecutionTaskPack:
        now = utcnow()
        tasks: list[ExecutionTask] = []
        blocks_publish = bool(approval and approval.blocks_publish)
        creative_has_blocked = bool(
            creative
            and any(
                _asset_state(a) is CreativeAssetState.BLOCKED
                for a in _iter_assets(creative)
            )
        )
        publish_globally_blocked = blocks_publish or creative_has_blocked

        # 1. Approval-driven tasks.
        approval_task_ids: list[str] = []
        if approval is not None:
            approval_task_ids = _approval_tasks(approval, tasks)

        # 2. Per-channel setup.
        channel_task_ids = _channel_setup_tasks(report, tasks)

        # 3. Per-creative-asset tasks.
        if creative is not None:
            _creative_tasks(
                creative,
                report,
                tasks,
                publish_globally_blocked=publish_globally_blocked,
                approval_task_ids=approval_task_ids,
            )

        # 4. SEO/GEO.
        _seo_tasks(report, tasks)

        # 5. Email marketing.
        if creative and creative.emails:
            _email_marketing_tasks(
                creative,
                tasks,
                publish_globally_blocked=publish_globally_blocked,
                approval_task_ids=approval_task_ids,
                channel_task_ids=channel_task_ids,
            )

        # 6. Social marketing.
        if creative and creative.social_posts:
            _social_marketing_tasks(
                tasks,
                publish_globally_blocked=publish_globally_blocked,
                approval_task_ids=approval_task_ids,
            )

        # 7. Design / visual.
        if visual is not None:
            _design_tasks(visual, tasks, publish_globally_blocked=publish_globally_blocked)
        elif creative is not None and creative.image_prompts:
            _design_tasks_from_creative(creative, tasks)

        # 8. Measurement.
        _measurement_tasks(report, tasks)

        # 9. Calendar checkpoints.
        _calendar_tasks(report, tasks)

        # Resolve transitive blocking: if a task depends on a blocked
        # task, it inherits BLOCKED too. Iterate to a fixed point.
        _propagate_blocking(tasks)

        return CampaignExecutionTaskPack(
            client_slug=report.client_slug,
            report_id=report.report_id,
            report_contract_version=report.contract_version,
            approval_pack_id=approval.pack_id if approval else None,
            approval_pack_contract_version=(
                approval.contract_version if approval else None
            ),
            creative_pack_id=creative.pack_id if creative else None,
            creative_pack_contract_version=(
                creative.contract_version if creative else None
            ),
            visual_pack_id=visual.pack_id if visual else None,
            visual_pack_contract_version=(
                visual.contract_version if visual else None
            ),
            blocks_publish=publish_globally_blocked,
            upstream_overall_state=(
                creative.derived_overall_state.value if creative else None
            ),
            tasks=tasks,
            created_at=now,
            updated_at=now,
            rule_set_id=DEFAULT_TASK_RULE_SET_ID,
        )

    def persist(self, pack: CampaignExecutionTaskPack) -> None:
        self._memory.put(
            pack.client_slug,
            EXECUTION_TASK_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )

    def load_latest(self, client_slug: str) -> CampaignExecutionTaskPack:
        raw = self._memory.get(client_slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
        return CampaignExecutionTaskPack.model_validate(raw)


def build_and_persist(
    memory: Memory,
    report: CampaignStrategyReport,
    approval: ApprovalPack | None,
    creative: CreativeAssetPack | None,
    visual: VisualDirectionPack | None,
) -> CampaignExecutionTaskPack:
    factory = TaskFactory(memory=memory)
    pack = factory.build(report, approval, creative, visual)
    factory.persist(pack)
    return pack


# ---------- internals ----------


def _iter_assets(creative: CreativeAssetPack):
    yield from creative.social_posts
    yield from creative.emails
    yield from creative.reels
    yield from creative.flyers
    yield from creative.image_prompts


def _asset_state(asset) -> CreativeAssetState:
    return asset.state


def _new_task(
    *,
    title: str,
    category: TaskCategory,
    priority: TaskPriority,
    state: TaskState = TaskState.TODO,
    description: str | None = None,
    channel: str | None = None,
    asset_kind: str | None = None,
    asset_ref: str | None = None,
    due_date: date | None = None,
    depends_on: list[str] | None = None,
    blocked_reason: str | None = None,
    owner_hint: str | None = None,
) -> ExecutionTask:
    return ExecutionTask(
        title=title,
        category=category,
        priority=priority,
        state=state,
        description=description,
        channel=channel,
        asset_kind=asset_kind,
        asset_ref=asset_ref,
        due_date=due_date,
        depends_on=list(depends_on or []),
        blocked_reason=blocked_reason,
        owner_hint=owner_hint,
    )


# ---------- generators ----------


def _approval_tasks(
    approval: ApprovalPack, sink: list[ExecutionTask]
) -> list[str]:
    """One task per approval-pack item the human must resolve.

    Returns the list of task ids so downstream PUBLISHING tasks can
    list them in ``depends_on``.
    """
    out: list[str] = []
    # Each unverified claim → HIGH priority approval task.
    for c in getattr(approval, "claims", []) or []:
        severity = getattr(c, "severity", "info")
        sev_value = getattr(severity, "value", severity)
        priority = (
            TaskPriority.HIGH
            if sev_value in _BLOCKER_SEVERITIES or sev_value in {"unsafe", "risky"}
            else TaskPriority.MEDIUM
        )
        t = _new_task(
            title=f"Revisar claim de approval-pack: '{_truncate(getattr(c, 'claim_text', '') or '', 120)}'",
            category=TaskCategory.APPROVAL,
            priority=priority,
            description=(
                f"Severidad declarada: {sev_value}. "
                f"Acción sugerida: {getattr(c, 'suggested_action', None) or 'revisar con compliance.'}"
            ),
            asset_kind="approval_claim",
            asset_ref=getattr(c, "claim_id", None),
            owner_hint="compliance_lead",
        )
        sink.append(t)
        out.append(t.task_id)

    # If the pack itself blocks publishing → a clear top-level task.
    if approval.blocks_publish:
        t = _new_task(
            title="Resolver bloqueo de publicación (Approval Pack)",
            category=TaskCategory.APPROVAL,
            priority=TaskPriority.HIGH,
            description=(
                "El Approval Pack está marcando blocks_publish=True. Antes "
                "de cualquier publicación, resolver los claims listados "
                "arriba y re-generar el pack."
            ),
            asset_kind="approval_pack",
            asset_ref=approval.pack_id,
            owner_hint="account_lead",
        )
        sink.append(t)
        out.append(t.task_id)

    return out


def _channel_setup_tasks(
    report: CampaignStrategyReport, sink: list[ExecutionTask]
) -> dict[str, str]:
    """Per-channel setup task. Returns ``{channel: task_id}`` so the
    publishing tasks can ``depends_on`` them."""
    out: dict[str, str] = {}
    for ch in report.channel_recommendation.channels:
        ch_value = ch.channel_type.value
        t = _new_task(
            title=f"Confirmar setup del canal {ch_value}",
            category=TaskCategory.OPERATIONAL,
            priority=TaskPriority.MEDIUM,
            description=(
                f"Validar handle/cuenta, accesos y cadencia ({ch.cadence_suggestion or 'a definir'}) "
                f"para {ch_value}. Rol esperado: {ch.expected_role or 'a definir'}."
            ),
            channel=ch_value,
            owner_hint="account_lead",
        )
        sink.append(t)
        out[ch_value] = t.task_id
    return out


def _creative_tasks(
    creative: CreativeAssetPack,
    report: CampaignStrategyReport,
    sink: list[ExecutionTask],
    *,
    publish_globally_blocked: bool,
    approval_task_ids: list[str],
) -> list[str]:
    """Per-asset QA + publish tasks. Returns the list of publish-task
    ids (used by the email / social marketing generators)."""
    publish_ids: list[str] = []

    def _qa_then_publish(
        *,
        asset_ref: str,
        asset_kind: str,
        title_base: str,
        channel: str | None,
    ) -> str:
        # QA: always TODO.
        qa = _new_task(
            title=f"QA copy de {title_base}",
            category=TaskCategory.SOCIAL if channel else TaskCategory.OPERATIONAL,
            priority=TaskPriority.MEDIUM,
            description=(
                "Revisar copy contra guía de marca, forbidden_words y bad_examples "
                "antes de pasar a publicación."
            ),
            channel=channel,
            asset_kind=asset_kind,
            asset_ref=asset_ref,
            owner_hint="copywriter",
        )
        sink.append(qa)
        # Publish: depends on QA + all approval tasks. Blocked if the
        # asset itself or the global publish flag is blocked.
        depends = [qa.task_id, *approval_task_ids]
        is_blocked = publish_globally_blocked
        publish = _new_task(
            title=f"Publicar / programar {title_base}",
            category=TaskCategory.PUBLISHING,
            priority=TaskPriority.HIGH if is_blocked else TaskPriority.MEDIUM,
            state=TaskState.BLOCKED if is_blocked else TaskState.TODO,
            blocked_reason=(
                "Approval Pack blocks publish o el asset está BLOCKED. "
                "Nada se publica hasta resolver el bloqueo."
            ) if is_blocked else None,
            description=(
                f"Cargar la pieza en la herramienta de publicación del canal "
                f"({channel or 'a definir'}) y agendar segun calendario."
            ),
            channel=channel,
            asset_kind=asset_kind,
            asset_ref=asset_ref,
            depends_on=depends,
            owner_hint="account_lead",
        )
        sink.append(publish)
        publish_ids.append(publish.task_id)
        return publish.task_id

    for post in creative.social_posts:
        _qa_then_publish(
            asset_ref=post.asset_id,
            asset_kind="social_post",
            title_base=f"social {post.channel.value} ({post.asset_id[:8]})",
            channel=post.channel.value,
        )
    for email in creative.emails:
        subject_preview = (
            email.subject_line_variants[0].subject
            if email.subject_line_variants
            else f"email step {email.step}"
        )
        _qa_then_publish(
            asset_ref=email.asset_id,
            asset_kind="email",
            title_base=f"email '{_truncate(subject_preview, 60)}'",
            channel="email",
        )
    for reel in creative.reels:
        _qa_then_publish(
            asset_ref=reel.asset_id,
            asset_kind="reels_script",
            title_base=f"reel '{_truncate(reel.title, 60)}'",
            channel="instagram",
        )
    for flyer in creative.flyers:
        headline_preview = (
            flyer.headline_variants[0].text
            if flyer.headline_variants
            else flyer.format.value
        )
        _qa_then_publish(
            asset_ref=flyer.asset_id,
            asset_kind="flyer_copy",
            title_base=f"flyer '{_truncate(headline_preview, 60)}'",
            channel=None,
        )

    # Image prompts get a render task (MEDIUM, never auto-blocked
    # because rendering is allowed even if publishing is blocked —
    # the operator may want to review images before approval).
    for img in creative.image_prompts:
        sink.append(
            _new_task(
                title=f"Renderizar imagen: '{_truncate(img.title, 60)}'",
                category=TaskCategory.DESIGN,
                priority=TaskPriority.MEDIUM,
                description=(
                    "Generar la imagen manualmente desde el prompt provisto. "
                    "MARKETING-AGENCY-OS no genera imágenes — esta tarea es "
                    "para una persona o herramienta externa."
                ),
                asset_kind="image_prompt",
                asset_ref=img.asset_id,
                owner_hint="designer",
            )
        )

    return publish_ids


def _seo_tasks(
    report: CampaignStrategyReport, sink: list[ExecutionTask]
) -> None:
    # One UTM scheme task for the whole campaign.
    sink.append(
        _new_task(
            title="Definir convención de UTMs para esta campaña",
            category=TaskCategory.SEO,
            priority=TaskPriority.MEDIUM,
            description=(
                "Documentar utm_source, utm_medium, utm_campaign, utm_content "
                "por canal. Aplicar en links de email y posts."
            ),
            owner_hint="account_lead",
        )
    )
    # Per-blog piece SEO task.
    for piece in report.suggested_pieces:
        if "blog" in piece.channel.value or piece.piece_type == "seo_article":
            sink.append(
                _new_task(
                    title=f"SEO básico para {piece.piece_type} en {piece.channel.value}",
                    category=TaskCategory.SEO,
                    priority=TaskPriority.MEDIUM,
                    description=(
                        "Title tag, meta description, slug, H1, alt text, "
                        "schema.org/Article. Validar con keyword cluster."
                    ),
                    channel=piece.channel.value,
                    asset_kind=piece.piece_type,
                    owner_hint="seo_specialist",
                )
            )


def _email_marketing_tasks(
    creative: CreativeAssetPack,
    sink: list[ExecutionTask],
    *,
    publish_globally_blocked: bool,
    approval_task_ids: list[str],
    channel_task_ids: dict[str, str],
) -> None:
    setup = _new_task(
        title="Configurar ESP y cargar secuencia de emails",
        category=TaskCategory.EMAIL,
        priority=TaskPriority.MEDIUM,
        description=(
            "Cargar la secuencia en el ESP elegido (provider local, no se "
            "envía nada desde el pipeline). Configurar listas y triggers."
        ),
        depends_on=[channel_task_ids[c] for c in ("email", "newsletter") if c in channel_task_ids],
        owner_hint="email_specialist",
    )
    sink.append(setup)
    for email in creative.emails:
        subject_preview = (
            email.subject_line_variants[0].subject
            if email.subject_line_variants
            else f"email step {email.step}"
        )
        sink.append(
            _new_task(
                title=f"Test de preview email '{_truncate(subject_preview, 60)}'",
                category=TaskCategory.EMAIL,
                priority=TaskPriority.MEDIUM,
                description="Test inbox preview en al menos 3 clientes (Gmail, Outlook, Apple Mail).",
                channel="email",
                asset_kind="email",
                asset_ref=email.asset_id,
                depends_on=[setup.task_id],
                owner_hint="email_specialist",
            )
        )


def _social_marketing_tasks(
    sink: list[ExecutionTask],
    *,
    publish_globally_blocked: bool,
    approval_task_ids: list[str],
) -> None:
    sink.append(
        _new_task(
            title="Configurar herramienta de scheduling social",
            category=TaskCategory.SOCIAL,
            priority=TaskPriority.MEDIUM,
            description=(
                "Definir herramienta (Buffer, Hootsuite, Later, o nativa). "
                "Cargar handles. Confirmar accesos."
            ),
            owner_hint="account_lead",
        )
    )
    sink.append(
        _new_task(
            title="Revisar hashtags por canal antes de publicar",
            category=TaskCategory.SOCIAL,
            priority=TaskPriority.LOW,
            description=(
                "Validar que los hashtags generados son apropiados por canal "
                "y no incluyen palabras prohibidas."
            ),
            owner_hint="account_lead",
        )
    )


def _design_tasks(
    visual: VisualDirectionPack,
    sink: list[ExecutionTask],
    *,
    publish_globally_blocked: bool,
) -> None:
    sink.append(
        _new_task(
            title="Aprobar dirección visual general",
            category=TaskCategory.DESIGN,
            priority=TaskPriority.HIGH,
            description=(
                "Revisar VisualDirectionPack con cliente: paleta, tipografía, "
                "tono visual, restricciones. Necesario antes de producción."
            ),
            asset_kind="visual_pack",
            asset_ref=visual.pack_id,
            owner_hint="creative_director",
        )
    )
    for d in getattr(visual, "directions", []) or []:
        sink.append(
            _new_task(
                title=f"Revisar dirección visual: '{_truncate(getattr(d, 'title', ''), 60)}'",
                category=TaskCategory.DESIGN,
                priority=TaskPriority.MEDIUM,
                description="Validar concepto, prompts y especificaciones técnicas.",
                asset_kind="visual_direction",
                asset_ref=getattr(d, "direction_id", None),
                owner_hint="creative_director",
            )
        )


def _design_tasks_from_creative(
    creative: CreativeAssetPack, sink: list[ExecutionTask]
) -> None:
    sink.append(
        _new_task(
            title="Revisar prompts de imagen y producir mocks",
            category=TaskCategory.DESIGN,
            priority=TaskPriority.MEDIUM,
            description=(
                f"{len(creative.image_prompts)} prompts a renderizar manualmente."
            ),
            owner_hint="designer",
        )
    )


def _measurement_tasks(
    report: CampaignStrategyReport, sink: list[ExecutionTask]
) -> None:
    sink.append(
        _new_task(
            title=f"Spec de tracking para KPI primario ({report.campaign_strategy.primary_kpi})",
            category=TaskCategory.MEASUREMENT,
            priority=TaskPriority.MEDIUM,
            description=(
                "Definir eventos, conversiones y dashboard. GA4 + provider stack. "
                "MARKETING-AGENCY-OS no conecta GA4 — esta tarea es un brief "
                "para que la persona/herramienta externa lo configure."
            ),
            owner_hint="analytics_lead",
        )
    )
    for kpi in report.campaign_strategy.secondary_kpis[:3]:
        sink.append(
            _new_task(
                title=f"Spec de tracking para KPI secundario: {kpi}",
                category=TaskCategory.MEASUREMENT,
                priority=TaskPriority.LOW,
                description="Definir evento, source y dashboard tile.",
                owner_hint="analytics_lead",
            )
        )


def _calendar_tasks(
    report: CampaignStrategyReport, sink: list[ExecutionTask]
) -> None:
    schedule = report.schedule
    start = schedule.start_date or (datetime.now(UTC).date() + timedelta(days=7))
    for week in range(1, schedule.weeks_total + 1):
        week_start = start + timedelta(weeks=week - 1)
        sink.append(
            _new_task(
                title=f"Checkpoint semana {week}: revisar piezas planeadas",
                category=TaskCategory.CALENDAR,
                priority=TaskPriority.LOW,
                description=(
                    f"Confirmar que las piezas planeadas para la semana {week} "
                    "están listas, aprobadas y agendadas."
                ),
                due_date=week_start,
                owner_hint="account_lead",
            )
        )


# ---------- post-processing ----------


def _propagate_blocking(tasks: list[ExecutionTask]) -> None:
    """If a task depends_on a blocked task, mark it blocked too.

    Iterates to a fixed point (handles chains: A blocked → B blocked
    because depends on A → C blocked because depends on B). Cycles
    are impossible by construction since the factory builds the
    dependency graph top-down.
    """
    by_id = {t.task_id: t for t in tasks}
    changed = True
    while changed:
        changed = False
        for t in tasks:
            if t.state is TaskState.BLOCKED:
                continue
            for dep_id in t.depends_on:
                dep = by_id.get(dep_id)
                if dep is None:
                    continue
                if dep.state is TaskState.BLOCKED:
                    t.state = TaskState.BLOCKED
                    t.blocked_reason = (
                        t.blocked_reason
                        or f"Bloqueado por dependencia: {dep_id} ({dep.title[:60]})"
                    )
                    changed = True
                    break


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


__all__ = [
    "DEFAULT_TASK_RULE_SET_ID",
    "EXECUTION_TASK_PACK_KIND",
    "SINGLETON_ID",
    "TaskFactory",
    "build_and_persist",
]
