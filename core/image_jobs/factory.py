"""ImageJobFactory — deterministic VisualDirectionPack → jobs translator.

Reads a persisted :class:`VisualDirectionPack` (MKT-3*) and emits
one :class:`ImageGenerationJob` per (piece direction, prompt
variant) pair.

**No image generation.** No HTTP. No SDK import. The factory only
materialises the jobs the agency will eventually run; a future
block (P-7A.6) will integrate a real provider.

State derivation (see :class:`ImageJobState` docstring):

- ApprovalPack ``blocks_publish=True`` → all jobs ``BLOCKED``.
- Source direction state == ``BLOCKED`` → job ``BLOCKED``.
- Source direction state == ``NEEDS_REVIEW`` → ``NEEDS_REVIEW``.
- Source direction state == ``READY_FOR_PUBLISH`` →
  ``READY_FOR_GENERATION``.
- Otherwise → ``DRAFT``.

``GENERATED`` is RESERVED and never emitted by this factory.

Provider suggestion is a deterministic heuristic from
``piece_type``:

- ``flyer_*`` / ``ad_creative`` → ``MIDJOURNEY`` (typography-heavy)
- ``email_header`` / ``landing_hero`` → ``OPENAI_IMAGES``
- ``reels_cover`` / ``instagram_*`` → ``REPLICATE`` (fast iter)
- ``linkedin_post_graphic`` / ``facebook_post`` → ``CANVA``
- fallback → ``MANUAL`` (operator decides; designer composes)
"""

from __future__ import annotations

import contextlib

from core.approval import APPROVAL_PACK_KIND, ApprovalPack
from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import (
    CREATIVE_PACK_KIND,
    CreativeAssetPack,
    CreativeAssetState,
)
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory
from core.pipeline.models import CampaignRunSummary
from core.pipeline.orchestrator import PIPELINE_RUN_KIND as CAMPAIGN_RUN_SUMMARY_KIND
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import (
    VISUAL_PACK_KIND,
    PieceVisualDirection,
    VisualChecklistItem,
    VisualDirectionPack,
    VisualPromptVariant,
)

from .models import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    SINGLETON_ID,
    ImageGenerationJob,
    ImageGenerationJobPack,
    ImageJobReviewChecklistItem,
    ImageJobState,
    ImageJobStats,
    ImageProviderSuggestion,
)

RUN_SUMMARY_SINGLETON = "current"
DEFAULT_IMAGE_JOB_FACTORY_RULE_SET_ID = "image-job-factory.v1"


# ---------- provider heuristic ----------


_PIECE_TYPE_TO_PROVIDER: dict[str, ImageProviderSuggestion] = {
    "flyer_square": ImageProviderSuggestion.MIDJOURNEY,
    "flyer_vertical": ImageProviderSuggestion.MIDJOURNEY,
    "ad_creative": ImageProviderSuggestion.MIDJOURNEY,
    "email_header": ImageProviderSuggestion.OPENAI_IMAGES,
    "landing_hero": ImageProviderSuggestion.OPENAI_IMAGES,
    "reels_cover": ImageProviderSuggestion.REPLICATE,
    "instagram_post": ImageProviderSuggestion.REPLICATE,
    "instagram_story": ImageProviderSuggestion.REPLICATE,
    "instagram_carousel": ImageProviderSuggestion.REPLICATE,
    "linkedin_post_graphic": ImageProviderSuggestion.CANVA,
    "facebook_post": ImageProviderSuggestion.CANVA,
}

_PROVIDER_RATIONALE: dict[ImageProviderSuggestion, str] = {
    ImageProviderSuggestion.MIDJOURNEY: (
        "Typography-heavy piece — manual designer touch usually needed."
    ),
    ImageProviderSuggestion.OPENAI_IMAGES: (
        "Hero / header piece — high-quality single image."
    ),
    ImageProviderSuggestion.REPLICATE: (
        "Fast-iteration social piece — multiple variants likely."
    ),
    ImageProviderSuggestion.CANVA: (
        "Brand-template piece — Canva keeps the agency template intact."
    ),
    ImageProviderSuggestion.STABILITY_AI: (
        "Stability fallback when other providers reject the prompt."
    ),
    ImageProviderSuggestion.MIDJOURNEY: (
        "Typography-heavy piece — manual designer touch usually needed."
    ),
    ImageProviderSuggestion.FIGMA: "Figma export — designer composes manually.",
    ImageProviderSuggestion.MANUAL: (
        "No provider hint matched — agency designer composes by hand."
    ),
}


# ---------- factory ----------


class ImageJobFactory:
    """Stateful factory over a Memory."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # --- public API ---

    def build(self, client_slug: str) -> ImageGenerationJobPack:
        visual = self._load_visual_pack(client_slug)
        approval = self._optional_load(
            client_slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON, ApprovalPack,
        )
        creative = self._optional_load(
            client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON, CreativeAssetPack,
        )
        run_summary = self._optional_load(
            client_slug, CAMPAIGN_RUN_SUMMARY_KIND, RUN_SUMMARY_SINGLETON,
            CampaignRunSummary,
        )

        approval_blocks = bool(getattr(approval, "blocks_publish", False))

        jobs: list[ImageGenerationJob] = []
        blocked_by_approval = 0
        blocked_by_direction = 0
        for direction in visual.directions:
            for variant in direction.prompt_variants:
                job, due_to_approval, due_to_direction = _build_job(
                    direction=direction,
                    variant=variant,
                    visual=visual,
                    approval_blocks=approval_blocks,
                )
                jobs.append(job)
                if due_to_approval:
                    blocked_by_approval += 1
                if due_to_direction:
                    blocked_by_direction += 1

        review = _build_pack_review_checklist(visual, approval_blocks)
        stats = _build_stats(
            jobs=jobs,
            directions=len(visual.directions),
            blocked_due_to_approval=blocked_by_approval,
            blocked_due_to_direction=blocked_by_direction,
        )

        return ImageGenerationJobPack(
            client_slug=client_slug,
            visual_pack_id=visual.pack_id,
            visual_pack_contract_version=visual.contract_version,
            creative_pack_id=getattr(creative, "pack_id", None),
            approval_pack_id=getattr(approval, "pack_id", None),
            run_summary_id=getattr(run_summary, "run_id", None),
            blocks_publish=approval_blocks or visual.blocks_publish,
            jobs=jobs,
            review_checklist=review,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=DEFAULT_IMAGE_JOB_FACTORY_RULE_SET_ID,
        )

    def persist(self, pack: ImageGenerationJobPack) -> None:
        self._memory.put(
            pack.client_slug,
            IMAGE_GENERATION_JOB_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        prev = self._memory.last_audit_hash(pack.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="image_job_factory",
            occurred_at=utcnow(),
            client_slug=pack.client_slug,
            payload={
                "image_generation_job_pack": {
                    "action": "built",
                    "pack_id": pack.pack_id,
                    "visual_pack_id": pack.visual_pack_id,
                    "creative_pack_id": pack.creative_pack_id,
                    "approval_pack_id": pack.approval_pack_id,
                    "total_jobs": pack.stats.total_jobs,
                    "blocks_publish": pack.blocks_publish,
                    "blocked_due_to_approval": (
                        pack.stats.blocked_due_to_approval
                    ),
                    "blocked_due_to_direction": (
                        pack.stats.blocked_due_to_direction
                    ),
                    "rule_set_id": pack.rule_set_id,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    # --- internals ---

    def _load_visual_pack(self, client_slug: str) -> VisualDirectionPack:
        try:
            raw = self._memory.get(client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON)
        except EntityNotFound as e:
            raise ValueError(
                f"no VisualDirectionPack for client {client_slug!r} — "
                "run the visual pipeline first."
            ) from e
        return VisualDirectionPack.model_validate(raw)

    def _optional_load(
        self,
        client_slug: str,
        kind: str,
        singleton_id: str,
        cls,
    ):
        with contextlib.suppress(EntityNotFound):
            return cls.model_validate(
                self._memory.get(client_slug, kind, singleton_id),
            )
        return None


def build_and_persist_image_jobs(
    memory: Memory, *, client_slug: str,
) -> ImageGenerationJobPack:
    factory = ImageJobFactory(memory=memory)
    pack = factory.build(client_slug)
    factory.persist(pack)
    return pack


# ---------- per-job builder ----------


def _build_job(
    *,
    direction: PieceVisualDirection,
    variant: VisualPromptVariant,
    visual: VisualDirectionPack,
    approval_blocks: bool,
) -> tuple[ImageGenerationJob, bool, bool]:
    """Build one job + return blocked-by-approval / blocked-by-direction flags."""

    state, blocked_reason, due_approval, due_direction = _derive_state(
        direction=direction, approval_blocks=approval_blocks,
        visual_blocks=visual.blocks_publish,
    )

    provider = _PIECE_TYPE_TO_PROVIDER.get(
        direction.piece_type.value, ImageProviderSuggestion.MANUAL,
    )
    provider_rationale = _PROVIDER_RATIONALE.get(provider)

    filename = _suggest_filename(
        client_slug=visual.client_slug,
        piece_type=direction.piece_type.value,
        variant_id=variant.variant_id,
    )

    checklist = _job_review_checklist(
        direction=direction, variant=variant, state=state,
    )

    return (
        ImageGenerationJob(
            piece_type=direction.piece_type.value,
            channel=(
                direction.channel.value if direction.channel else None
            ),
            direction_id=direction.direction_id,
            variant_id=variant.variant_id,
            creative_ref=direction.source_creative_asset_id,
            image_prompt_ref=direction.source_creative_image_prompt_id,
            prompt=variant.full_prompt_text,
            negative_prompt=variant.negative_prompt,
            aspect_ratio=variant.aspect_ratio,
            dimensions_px=direction.spec.dimensions_px,
            in_image_text=list(variant.in_image_text),
            visual_style=variant.visual_style,
            intended_use=variant.intended_use,
            output_filename_suggestion=filename,
            provider_suggestion=provider,
            provider_rationale=provider_rationale,
            state=state,
            blocked_reason=blocked_reason,
            review_checklist=checklist,
        ),
        due_approval,
        due_direction,
    )


def _derive_state(
    *,
    direction: PieceVisualDirection,
    approval_blocks: bool,
    visual_blocks: bool,
) -> tuple[ImageJobState, str | None, bool, bool]:
    if approval_blocks:
        return (
            ImageJobState.BLOCKED,
            "Approval pack blocks publish.",
            True, False,
        )
    if direction.state is CreativeAssetState.BLOCKED:
        return (
            ImageJobState.BLOCKED,
            "Source visual direction is BLOCKED.",
            False, True,
        )
    if visual_blocks:
        return (
            ImageJobState.BLOCKED,
            "Visual pack flag blocks_publish=True.",
            False, True,
        )
    if direction.state is CreativeAssetState.NEEDS_REVIEW:
        return (
            ImageJobState.NEEDS_REVIEW,
            None, False, False,
        )
    if direction.state is CreativeAssetState.READY_FOR_PUBLISH:
        return (
            ImageJobState.READY_FOR_GENERATION,
            None, False, False,
        )
    return (ImageJobState.DRAFT, None, False, False)


def _suggest_filename(
    *, client_slug: str, piece_type: str, variant_id: str,
) -> str:
    safe_variant = "".join(
        ch for ch in variant_id if ch.isalnum() or ch in ("-", "_")
    ) or "v1"
    return f"{client_slug}--{piece_type}--{safe_variant}.png"


def _job_review_checklist(
    *,
    direction: PieceVisualDirection,
    variant: VisualPromptVariant,
    state: ImageJobState,
) -> list[ImageJobReviewChecklistItem]:
    items: list[ImageJobReviewChecklistItem] = []
    # Copy the source direction checklist verbatim.
    for src in direction.checklist:
        items.append(_checklist_from_source(src))
    # Job-specific items.
    if variant.in_image_text:
        items.append(ImageJobReviewChecklistItem(
            title=f"Verify in-image text spelling: {variant.in_image_text}",
            severity="warning",
            rationale="Provider OCR errors are common; manual proof read.",
        ))
    items.append(ImageJobReviewChecklistItem(
        title=f"Confirm dimensions match {direction.spec.dimensions_px}",
        severity="info",
        rationale=(
            "Aspect ratio + pixel size must match the channel spec or "
            "the asset will be down-scaled at delivery."
        ),
    ))
    if state is ImageJobState.BLOCKED:
        items.append(ImageJobReviewChecklistItem(
            title="Resolve upstream block before submitting to provider.",
            severity="blocker",
            rationale=(
                "Job is BLOCKED — do NOT submit to any provider until "
                "the upstream approval / visual direction unblocks."
            ),
        ))
    return items


def _checklist_from_source(src: VisualChecklistItem) -> ImageJobReviewChecklistItem:
    return ImageJobReviewChecklistItem(
        title=src.title,
        severity="info",
        rationale=None,
    )


def _build_pack_review_checklist(
    visual: VisualDirectionPack, approval_blocks: bool,
) -> list[ImageJobReviewChecklistItem]:
    items: list[ImageJobReviewChecklistItem] = []
    for src in visual.global_checklist:
        items.append(_checklist_from_source(src))
    if approval_blocks:
        items.append(ImageJobReviewChecklistItem(
            title="Approval pack blocks publish — every job is BLOCKED.",
            severity="blocker",
            rationale="Resolve approval before generating any image.",
        ))
    if visual.blocks_publish:
        items.append(ImageJobReviewChecklistItem(
            title="Visual pack blocks_publish=True — review every job.",
            severity="blocker",
            rationale="Visual pack flagged the campaign as blocking.",
        ))
    return items


def _build_stats(
    *,
    jobs: list[ImageGenerationJob],
    directions: int,
    blocked_due_to_approval: int,
    blocked_due_to_direction: int,
) -> ImageJobStats:
    by_state: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    by_piece: dict[str, int] = {}
    for j in jobs:
        by_state[j.state.value] = by_state.get(j.state.value, 0) + 1
        by_provider[j.provider_suggestion.value] = (
            by_provider.get(j.provider_suggestion.value, 0) + 1
        )
        by_piece[j.piece_type] = by_piece.get(j.piece_type, 0) + 1
    return ImageJobStats(
        total_jobs=len(jobs),
        by_state=by_state,
        by_provider_suggestion=by_provider,
        by_piece_type=by_piece,
        directions_consumed=directions,
        blocked_due_to_approval=blocked_due_to_approval,
        blocked_due_to_direction=blocked_due_to_direction,
    )


__all__ = [
    "DEFAULT_IMAGE_JOB_FACTORY_RULE_SET_ID",
    "ImageJobFactory",
    "build_and_persist_image_jobs",
]
