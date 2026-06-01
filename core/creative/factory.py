"""CreativeFactory — builds, persists, and audits a Creative Asset Pack.

The factory:
1. Reads a :class:`CampaignStrategyReport` and (optionally) an
   :class:`ApprovalPack`.
2. Derives the per-asset state from the approval pack (or a conservative
   default when none is present).
3. Generates assets and A/B variants deterministically from templates.
4. Schedules every asset on a per-piece calendar.
5. Persists the resulting :class:`CreativeAssetPack` to memory and emits an
   audit event.

No LLM. No external APIs. No image generation. No publishing.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core.approval.models import ApprovalPack, ApprovalState
from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.domain.enums import ClaimSeverity
from core.memory import Memory
from core.strategy.models import CampaignStrategyReport

from .calendar import schedule_assets
from .models import (
    CREATIVE_PACK_VERSION,
    AssetChecklistItem,
    CreativeAssetPack,
    CreativeAssetState,
    CTAStyle,
    CTAVariant,
    EmailAsset,
    FlyerAsset,
    FlyerFormat,
    HeadlineStyle,
    HeadlineVariant,
    HookVariant,
    ImagePromptAsset,
    ReelsAsset,
    SocialPostAsset,
    SubjectLineVariant,
    SubjectStyle,
    VariantAngle,
)

CREATIVE_PACK_KIND = "creative_asset_pack"
SINGLETON_ID = "current"

# Identifier of the default template set, persisted on the pack so a future
# re-run with a different set is auditable.
DEFAULT_TEMPLATE_SET_ID = "default-templates.v1"


# ---------- Helpers ----------

def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def _derive_state_for_assets(pack: ApprovalPack | None) -> CreativeAssetState:
    """Pick the default per-asset state from the approval pack."""
    if pack is None:
        # Conservative default when there is no audit on record.
        return CreativeAssetState.NEEDS_REVIEW
    if pack.blocks_publish:
        return CreativeAssetState.BLOCKED
    if pack.state is ApprovalState.APPROVED:
        return CreativeAssetState.READY_FOR_PUBLISH
    if pack.overall_severity in (ClaimSeverity.RISKY, ClaimSeverity.UNSAFE):
        return CreativeAssetState.NEEDS_REVIEW
    return CreativeAssetState.DRAFT


def _checklist_for_asset(state: CreativeAssetState, kind_label: str) -> list[AssetChecklistItem]:
    items: list[AssetChecklistItem] = [
        AssetChecklistItem(
            title=f"Revisar tono y voz de marca en este {kind_label}.",
            severity="must",
        ),
        AssetChecklistItem(
            title="Verificar claims, números y comparaciones contra fuente.",
            severity="must",
        ),
    ]
    if state is CreativeAssetState.BLOCKED:
        items.append(
            AssetChecklistItem(
                title="BLOQUEADO: revisar Approval Pack y resolver claims antes de avanzar.",
                severity="blocker",
            )
        )
    elif state is CreativeAssetState.NEEDS_REVIEW:
        items.append(
            AssetChecklistItem(
                title="Decisión humana pendiente antes de publicar.",
                severity="must",
            )
        )
    elif state is CreativeAssetState.READY_FOR_PUBLISH:
        items.append(
            AssetChecklistItem(
                title="Aprobado — confirmar canal y handle antes de enviar a producción.",
                severity="should",
            )
        )
    return items


def _campaign_window(report: CampaignStrategyReport) -> tuple[date, date]:
    """Return ``(start, end)``. Falls back to today + duration when missing."""
    start = report.schedule.start_date or date.today()
    end = report.schedule.end_date or (
        start + timedelta(weeks=report.campaign_strategy.duration_weeks)
    )
    if end < start:
        end = start + timedelta(weeks=1)
    return start, end


# ---------- Variant generators ----------

def _hook_variants_for_post(
    base_hook: str,
    audience_label: str,
    product_name: str,
    differentiator: str,
) -> list[HookVariant]:
    """Two deterministic hook variants per post: contrast + curiosity."""
    return [
        HookVariant(
            variant_id="A",
            text=_truncate(base_hook or f"{product_name} para {audience_label}.", 400),
            angle=VariantAngle.CONTRAST,
        ),
        HookVariant(
            variant_id="B",
            text=_truncate(
                f"3 razones por las que {audience_label} eligen {product_name}: {differentiator}.",
                400,
            ),
            angle=VariantAngle.CURIOSITY,
        ),
    ]


def _cta_variants_for_post(product_name: str) -> list[CTAVariant]:
    return [
        CTAVariant(variant_id="A", text="Probalo gratis", style=CTAStyle.DIRECT),
        CTAVariant(
            variant_id="B",
            text=f"Mirá cómo funciona {product_name}",
            style=CTAStyle.LOW_FRICTION,
        ),
    ]


def _subject_variants_for_email(
    base_subject: str,
    product_name: str,
    step: int,
) -> list[SubjectLineVariant]:
    """Two subject variants per email."""
    preview = "Lo importante en 60 segundos."
    return [
        SubjectLineVariant(
            variant_id="A",
            subject=_truncate(base_subject or f"{product_name} — paso {step}", 80),
            preview_text=_truncate(preview, 140),
            style=SubjectStyle.DIRECT,
        ),
        SubjectLineVariant(
            variant_id="B",
            subject=_truncate(f"¿Qué cambia con {product_name}? (paso {step})", 80),
            preview_text=_truncate("Te lo cuento en 4 puntos.", 140),
            style=SubjectStyle.QUESTION,
        ),
    ]


def _headline_variants_for_flyer(
    product_name: str,
    differentiator: str,
    audience_label: str,
) -> list[HeadlineVariant]:
    return [
        HeadlineVariant(
            variant_id="A",
            text=_truncate(f"{product_name}: {differentiator}.", 200),
            style=HeadlineStyle.BENEFIT,
        ),
        HeadlineVariant(
            variant_id="B",
            text=_truncate(
                f"Hecho para {audience_label}. Por una razón.", 200
            ),
            style=HeadlineStyle.POV,
        ),
    ]


def _hook_variants_for_reels(base_hook: str, audience_label: str) -> list[HookVariant]:
    return [
        HookVariant(
            variant_id="A",
            text=_truncate(base_hook or f"Si sos {audience_label.lower()}, mirá esto.", 400),
            angle=VariantAngle.CURIOSITY,
        ),
        HookVariant(
            variant_id="B",
            text=_truncate(
                f"3 errores que {audience_label.lower()} comete al empezar — y cómo evitarlos.",
                400,
            ),
            angle=VariantAngle.DATA,
        ),
    ]


# ---------- Builder ----------

class CreativeFactory:
    """Produce a :class:`CreativeAssetPack` from a report + optional approval pack."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # ---------- build ----------

    def build(
        self,
        report: CampaignStrategyReport,
        approval_pack: ApprovalPack | None = None,
    ) -> CreativeAssetPack:
        client_slug = report.client_slug
        default_state = _derive_state_for_assets(approval_pack)
        blocks_publish = (
            approval_pack.blocks_publish if approval_pack is not None else False
        )

        start_date, end_date = _campaign_window(report)
        product_name = report.executive_summary.headline.split(":")[0].split(".")[0].strip() or "tu producto"
        audience_label = report.target_audience.label
        differentiator = (
            report.value_proposition.differentiators[0]
            if report.value_proposition.differentiators
            else report.value_proposition.headline
        )

        # ---- social posts ----
        social_posts: list[SocialPostAsset] = []
        # Use up to top-3 channels from the recommendation.
        for ch_entry in report.channel_recommendation.channels[:3]:
            # Find the matching draft text from MKT-3A, if any.
            matching = [
                p for p in report.social_post_drafts if p.channel == ch_entry.channel_type
            ]
            base_hook = matching[0].hook if matching else f"{product_name} para {audience_label}."
            base_body = (
                matching[0].body
                if matching
                else f"{report.value_proposition.headline}\n\n{differentiator}."
            )
            base_hashtags = (
                matching[0].hashtags
                if matching
                else report.keyword_plan.hashtags[:5]
            )
            # Two posts per channel (variant batches).
            for batch in range(2):
                asset = SocialPostAsset(
                    channel=ch_entry.channel_type,
                    hook_variants=_hook_variants_for_post(
                        base_hook=f"{base_hook} (#{batch + 1})",
                        audience_label=audience_label,
                        product_name=product_name,
                        differentiator=differentiator,
                    ),
                    body=base_body,
                    cta_variants=_cta_variants_for_post(product_name),
                    caption_cross_post=_truncate(
                        f"{base_hook} — {report.value_proposition.headline}",
                        500,
                    ),
                    hashtags=base_hashtags,
                    state=default_state,
                )
                asset.checklist = _checklist_for_asset(default_state, f"social post ({ch_entry.channel_type.value})")
                social_posts.append(asset)

        # ---- emails ----
        emails: list[EmailAsset] = []
        for src_email in report.email_sequence.emails:
            email_asset = EmailAsset(
                step=src_email.step,
                subject_line_variants=_subject_variants_for_email(
                    base_subject=src_email.subject,
                    product_name=product_name,
                    step=src_email.step,
                ),
                body=src_email.body,
                cta=src_email.cta,
                send_after_days=src_email.send_after_days,
                state=default_state,
            )
            email_asset.checklist = _checklist_for_asset(default_state, "email")
            emails.append(email_asset)

        # ---- reels ----
        reels: list[ReelsAsset] = []
        for src in report.reels_script_pack.scripts:
            # Defensive: ReelsScriptEntry.title has no length cap upstream,
            # but ReelsAsset.title is capped at 200 chars. Truncate so a
            # long Claude- or template-generated title never crashes the
            # creative stage. Discovered in MKT-4C with a real intake.
            reel_title = (
                src.title if len(src.title) <= 200
                else src.title[:197].rstrip() + "..."
            )
            reel = ReelsAsset(
                title=reel_title,
                hook_variants=_hook_variants_for_reels(src.hook, audience_label),
                beats=list(src.beats) or ["0-3s: hook", "3-25s: desarrollo", "25-30s: CTA"],
                voiceover_lines=list(src.voiceover_lines),
                on_screen_text=list(src.on_screen_text),
                cta=src.cta,
                target_duration_s=src.target_duration_s,
                state=default_state,
            )
            reel.checklist = _checklist_for_asset(default_state, "reels script")
            reels.append(reel)

        # ---- flyers ----
        flyers: list[FlyerAsset] = []
        for fmt in (FlyerFormat.SQUARE, FlyerFormat.PORTRAIT_4_5, FlyerFormat.STORY_9_16):
            flyer = FlyerAsset(
                format=fmt,
                headline_variants=_headline_variants_for_flyer(
                    product_name=product_name,
                    differentiator=differentiator,
                    audience_label=audience_label,
                ),
                subhead=_truncate(
                    f"Para {audience_label}. {differentiator}.",
                    300,
                ),
                body=_truncate(
                    f"{report.value_proposition.headline}\n\n"
                    + "\n".join(f"• {p}" for p in report.value_proposition.differentiators[:3]),
                    1500,
                ),
                cta="Empezá hoy",
                state=default_state,
            )
            flyer.checklist = _checklist_for_asset(default_state, f"flyer {fmt.value}")
            flyers.append(flyer)

        # ---- image prompts ----
        image_prompts = self._image_prompts_from_report(report, default_state, product_name, audience_label)

        # ---- calendar ----
        calendar, asset_dates = schedule_assets(
            social_posts=social_posts,
            emails=emails,
            reels=reels,
            flyers=flyers,
            start_date=start_date,
            end_date=end_date,
        )
        # Backfill `scheduled_for` on assets.
        for asset_list in (social_posts, emails, reels, flyers):
            for a in asset_list:
                a.scheduled_for = asset_dates.get(a.asset_id)

        now = utcnow()
        pack = CreativeAssetPack(
            contract_version=CREATIVE_PACK_VERSION,
            client_slug=client_slug,
            report_id=report.report_id,
            report_contract_version=report.contract_version,
            approval_pack_id=approval_pack.pack_id if approval_pack else None,
            approval_pack_contract_version=(
                approval_pack.contract_version if approval_pack else None
            ),
            derived_overall_state=default_state,
            blocks_publish=blocks_publish,
            social_posts=social_posts,
            emails=emails,
            reels=reels,
            flyers=flyers,
            image_prompts=image_prompts,
            calendar=calendar,
            created_at=now,
            updated_at=now,
            rule_set_id=DEFAULT_TEMPLATE_SET_ID,
        )
        return pack

    # ---------- persistence ----------

    def persist(self, pack: CreativeAssetPack) -> None:
        existed = self._memory.exists(
            pack.client_slug, CREATIVE_PACK_KIND, SINGLETON_ID
        )
        self._memory.put(
            pack.client_slug,
            CREATIVE_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        self._emit_event(
            client_slug=pack.client_slug,
            payload={
                "pack_id": pack.pack_id,
                "report_id": pack.report_id,
                "approval_pack_id": pack.approval_pack_id,
                "derived_overall_state": pack.derived_overall_state.value,
                "blocks_publish": pack.blocks_publish,
                "total_assets": pack.total_assets,
                "action": "updated" if existed else "created",
            },
        )

    def load(self, client_slug: str) -> CreativeAssetPack:
        raw = self._memory.get(client_slug, CREATIVE_PACK_KIND, SINGLETON_ID)
        return CreativeAssetPack.model_validate(raw)

    # ---------- internals ----------

    def _image_prompts_from_report(
        self,
        report: CampaignStrategyReport,
        state: CreativeAssetState,
        product_name: str,
        audience_label: str,
    ) -> list[ImagePromptAsset]:
        prompts: list[ImagePromptAsset] = []

        for src in report.creative_brief_pack.briefs:
            asset = ImagePromptAsset(
                title=src.title,
                intended_use=src.piece_type,
                prompt_text=src.prompt_for_image_model,
                negative_prompt=(
                    "no stock-photo cliché handshakes, no clip-art icons, "
                    "no purple gradient backgrounds, no watermarks, "
                    "no readable competitor logos"
                ),
                aspect_ratio=src.aspect_ratio,
                style_notes=src.typography_hint,
                palette_hint=list(src.palette_hint),
                accessibility_notes=list(src.accessibility_notes),
                state=state,
            )
            asset.checklist = _checklist_for_asset(state, "image prompt")
            prompts.append(asset)

        # Bonus prompt: OOH-style hero image not present in MKT-3A.
        ooh = ImagePromptAsset(
            title="OOH / billboard hero",
            intended_use="ooh_billboard",
            prompt_text=(
                f"Bold OOH-style hero image. Single subject representing {audience_label}. "
                f"Product context: {product_name}. Editorial photography, strong contrast, "
                "negative space top-left for headline overlay. 16:9 aspect."
            ),
            negative_prompt="no cluttered backgrounds, no small text, no UI mockups",
            aspect_ratio="16:9",
            style_notes="High-contrast editorial; minimal palette.",
            palette_hint=["#0F172A", "#22D3EE", "#F8FAFC"],
            accessibility_notes=["Headline contrast AA min"],
            state=state,
        )
        ooh.checklist = _checklist_for_asset(state, "image prompt (OOH)")
        prompts.append(ooh)

        return prompts

    def _emit_event(
        self, *, client_slug: str, payload: dict[str, Any]
    ) -> None:
        prev = self._memory.last_audit_hash(client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="creative_factory",
            occurred_at=utcnow(),
            client_slug=client_slug,
            payload={"creative_pack": payload},
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)


# ---------- Convenience pipeline ----------

def build_and_persist(
    memory: Memory,
    report: CampaignStrategyReport,
    approval_pack: ApprovalPack | None = None,
) -> CreativeAssetPack:
    factory = CreativeFactory(memory)
    pack = factory.build(report, approval_pack)
    factory.persist(pack)
    return pack


__all__ = [
    "CREATIVE_PACK_KIND",
    "SINGLETON_ID",
    "DEFAULT_TEMPLATE_SET_ID",
    "CreativeFactory",
    "build_and_persist",
]
