"""ImageProviderPlanner — deterministic provider scorer + dry-run engine.

Reads the persisted MKT-7A :class:`ImageGenerationJobPack`, scores
each candidate provider against a fixed weight set per piece type,
emits per-job recommendations + dry-run receipts.

**No HTTP. No SDK import. No credential read. No image generation.**
Dry-run receipts carry the *shape* of the request the operator
would eventually send — never a real URL or credential.
"""

from __future__ import annotations

import contextlib

from core.approval import APPROVAL_PACK_KIND, ApprovalPack
from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.domain.base import utcnow
from core.image_jobs.models import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    ImageGenerationJob,
    ImageGenerationJobPack,
    ImageJobState,
)
from core.image_jobs.models import (
    SINGLETON_ID as JOB_PACK_SINGLETON,
)
from core.memory import EntityNotFound, Memory
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

from .models import (
    IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND,
    SINGLETON_ID,
    ImageProviderRecommendation,
    ImageProviderRecommendationPack,
    ImageProviderRecommendationStats,
    ProviderCriterionScore,
    ProviderDryRunReceipt,
    ProviderDryRunStatus,
    ProviderEvaluation,
)
from .profiles import (
    DEFAULT_PROVIDER_PROFILES,
    PROVIDER_CRITERIA,
    ImageProviderProfile,
)

DEFAULT_PROVIDER_PLANNER_RULE_SET_ID = "image-provider-planner.v1"

# Per-piece-type weight overlays — bumps that bias scoring towards
# what matters most for that piece. Each value is added to the
# base weighted score for the criterion. Tracked as P-7B.4 for
# per-tenant overrides.
_PIECE_TYPE_WEIGHT_OVERLAYS: dict[str, dict[str, float]] = {
    # Hero / landing / email pieces — quality + commercial use are
    # the things that move the needle.
    "landing_hero": {"expected_quality": 1.5, "style_control": 0.5},
    "email_header": {"expected_quality": 1.0, "style_control": 0.5},
    # Ads / flyers — typography control + low artifact risk.
    "ad_creative": {"style_control": 1.5, "artifact_risk": 1.0},
    "flyer_square": {"style_control": 1.5, "artifact_risk": 1.0},
    "flyer_vertical": {"style_control": 1.5, "artifact_risk": 1.0},
    # Social pieces — cost + format flexibility + iteration speed.
    "instagram_post": {"cost": 1.0, "format_aspect_support": 0.5},
    "instagram_story": {"cost": 1.0, "format_aspect_support": 0.5},
    "instagram_carousel": {"cost": 1.0, "format_aspect_support": 0.5},
    "reels_cover": {"cost": 1.0, "format_aspect_support": 0.5},
    "linkedin_post_graphic": {
        "commercial_use": 1.0, "artifact_risk": 0.5,
    },
    "facebook_post": {"cost": 0.5, "commercial_use": 0.5},
}

# Base weights — applied to every piece type unless overridden by
# the per-tenant config (P-7B.4).
_BASE_WEIGHTS: dict[str, float] = {
    "expected_quality": 1.0,
    "cost": 0.8,
    "api_support": 0.8,
    "format_aspect_support": 0.6,
    "integration_ease": 0.7,
    "security": 0.5,
    "style_control": 0.8,
    "artifact_risk": 0.7,
    "commercial_use": 1.0,
    "external_dependency": 0.5,
}

# Score floor — when no provider scores above this, the planner
# falls back to MANUAL.
_FALLBACK_SCORE_FLOOR = 12.0


class ImageProviderPlanner:
    """Reads a persisted job pack and emits a recommendation pack."""

    def __init__(
        self,
        memory: Memory,
        *,
        profiles: dict[str, ImageProviderProfile] | None = None,
    ) -> None:
        self._memory = memory
        self._profiles = profiles or DEFAULT_PROVIDER_PROFILES

    # ---------- public ----------

    def plan(self, client_slug: str) -> ImageProviderRecommendationPack:
        job_pack = self._load_job_pack(client_slug)
        visual = self._optional_load(
            client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON, VisualDirectionPack,
        )
        creative = self._optional_load(
            client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON, CreativeAssetPack,
        )
        approval = self._optional_load(
            client_slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON, ApprovalPack,
        )

        evaluations = self._build_evaluations()
        recommendations: list[ImageProviderRecommendation] = []
        receipts: list[ProviderDryRunReceipt] = []
        overrode = 0
        skipped_blocked = 0
        skipped_manual = 0
        total_cost = 0.0

        for job in job_pack.jobs:
            rec, receipt = self._plan_one(job)
            recommendations.append(rec)
            receipts.append(receipt)
            total_cost += rec.estimated_cost_usd
            if rec.recommended_provider != job.provider_suggestion.value:
                overrode += 1
            if receipt.status is ProviderDryRunStatus.SKIPPED_BLOCKED:
                skipped_blocked += 1
            elif receipt.status is ProviderDryRunStatus.SKIPPED_MANUAL:
                skipped_manual += 1

        stats = _build_stats(
            recommendations=recommendations,
            receipts=receipts,
            overrode_job_suggestion=overrode,
            skipped_blocked=skipped_blocked,
            skipped_manual=skipped_manual,
            total_cost=total_cost,
        )

        return ImageProviderRecommendationPack(
            client_slug=client_slug,
            job_pack_id=job_pack.pack_id,
            job_pack_contract_version=job_pack.contract_version,
            visual_pack_id=getattr(visual, "pack_id", None),
            creative_pack_id=getattr(creative, "pack_id", None),
            approval_pack_id=getattr(approval, "pack_id", None),
            blocks_publish=job_pack.blocks_publish,
            evaluations=evaluations,
            recommendations=recommendations,
            dry_run_receipts=receipts,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=DEFAULT_PROVIDER_PLANNER_RULE_SET_ID,
        )

    def persist(self, pack: ImageProviderRecommendationPack) -> None:
        self._memory.put(
            pack.client_slug,
            IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        prev = self._memory.last_audit_hash(pack.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="image_provider_planner",
            occurred_at=utcnow(),
            client_slug=pack.client_slug,
            payload={
                "image_provider_recommendation_pack": {
                    "action": "planned",
                    "pack_id": pack.pack_id,
                    "job_pack_id": pack.job_pack_id,
                    "total_jobs": pack.stats.total_jobs,
                    "overrode_job_suggestion": pack.stats.overrode_job_suggestion,
                    "skipped_blocked": pack.stats.skipped_blocked,
                    "skipped_manual": pack.stats.skipped_manual,
                    "total_estimated_cost_usd": round(
                        pack.stats.total_estimated_cost_usd, 4,
                    ),
                    "rule_set_id": pack.rule_set_id,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    # ---------- internals ----------

    def _load_job_pack(self, client_slug: str) -> ImageGenerationJobPack:
        try:
            raw = self._memory.get(
                client_slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON,
            )
        except EntityNotFound as e:
            raise ValueError(
                f"no ImageGenerationJobPack for client {client_slug!r} — "
                "run `mkt image-jobs` first."
            ) from e
        return ImageGenerationJobPack.model_validate(raw)

    def _optional_load(
        self, client_slug: str, kind: str, singleton: str, cls,
    ):
        with contextlib.suppress(EntityNotFound):
            return cls.model_validate(
                self._memory.get(client_slug, kind, singleton),
            )
        return None

    def _build_evaluations(self) -> list[ProviderEvaluation]:
        out: list[ProviderEvaluation] = []
        for name, profile in self._profiles.items():
            scores = [
                ProviderCriterionScore(
                    criterion=c,
                    score=profile.scores.get(c).score
                    if profile.scores.get(c) else 0,
                    note=(
                        profile.scores.get(c).note
                        if profile.scores.get(c) and profile.scores.get(c).note
                        else None
                    ),
                )
                for c in PROVIDER_CRITERIA
            ]
            out.append(ProviderEvaluation(
                provider=name,
                scores=scores,
                estimated_cost_usd_per_image=profile.estimated_cost_usd_per_image,
                commercial_use_ok=profile.commercial_use_ok,
                credentials_required=list(profile.credentials_required),
                supported_aspect_ratios=list(profile.supported_aspect_ratios),
                supported_formats=list(profile.supported_formats),
                integration_difficulty=profile.integration_difficulty,
                external_dependency_risk=profile.external_dependency_risk,
                notes=profile.notes,
            ))
        # Deterministic order: provider name asc.
        out.sort(key=lambda e: e.provider)
        return out

    def _plan_one(
        self, job: ImageGenerationJob,
    ) -> tuple[ImageProviderRecommendation, ProviderDryRunReceipt]:
        # Score every provider for this piece type. Skip providers
        # whose aspect_ratio set excludes the job's ratio.
        scored: list[tuple[str, float, ImageProviderProfile]] = []
        for name, profile in self._profiles.items():
            if not _provider_supports_aspect(profile, job.aspect_ratio):
                continue
            total = _weighted_score(profile, job.piece_type)
            scored.append((name, total, profile))

        # Sort by total desc, then by provider name for determinism.
        scored.sort(key=lambda t: (-t[1], t[0]))

        if not scored or scored[0][1] < _FALLBACK_SCORE_FLOOR:
            recommended = "manual"
            recommended_score = (
                scored[0][1] if scored else 0.0
            )
            alternatives = [
                name for name, _, _ in scored
                if name != "manual"
            ][:3]
        else:
            recommended = scored[0][0]
            recommended_score = scored[0][1]
            alternatives = [
                name for name, _, _ in scored[1:4]
                if name != recommended
            ]

        rec_profile = self._profiles[recommended]
        rationale = _build_rationale(
            recommended=recommended, score=recommended_score,
            job=job, profile=rec_profile,
        )
        risk_notes = _build_risk_notes(
            recommended=recommended, profile=rec_profile, job=job,
        )

        recommendation = ImageProviderRecommendation(
            job_id=job.job_id,
            piece_type=job.piece_type,
            job_state=job.state.value,
            job_provider_suggestion=job.provider_suggestion.value,
            recommended_provider=recommended,
            recommended_score=round(recommended_score, 3),
            alternative_providers=alternatives,
            fallback_provider="manual",
            rationale=rationale,
            risk_notes=risk_notes,
            estimated_cost_usd=round(
                rec_profile.estimated_cost_usd_per_image, 4,
            ),
        )

        receipt = self._dry_run_receipt(job, recommended, rec_profile)
        return recommendation, receipt

    def _dry_run_receipt(
        self,
        job: ImageGenerationJob,
        recommended: str,
        profile: ImageProviderProfile,
    ) -> ProviderDryRunReceipt:
        if job.state is ImageJobState.BLOCKED:
            return ProviderDryRunReceipt(
                job_id=job.job_id,
                provider=recommended,
                status=ProviderDryRunStatus.SKIPPED_BLOCKED,
                reason=(
                    job.blocked_reason
                    or "Job is BLOCKED — no dry-run preview generated."
                ),
                model_hint=profile.model_hint,
                prompt_length_chars=len(job.prompt),
                aspect_ratio=job.aspect_ratio,
                dimensions_px=job.dimensions_px,
                simulated_output_filename=job.output_filename_suggestion,
                notes=(
                    "Resolve upstream block before requesting a real "
                    "preview."
                ),
            )
        if recommended == "manual":
            return ProviderDryRunReceipt(
                job_id=job.job_id,
                provider="manual",
                status=ProviderDryRunStatus.SKIPPED_MANUAL,
                reason=(
                    "Recommended path is manual — no provider request "
                    "to dry-run."
                ),
                model_hint=profile.model_hint,
                prompt_length_chars=len(job.prompt),
                aspect_ratio=job.aspect_ratio,
                dimensions_px=job.dimensions_px,
                simulated_output_filename=job.output_filename_suggestion,
                notes=(
                    "Agency designer composes manually — see review "
                    "checklist."
                ),
            )
        return ProviderDryRunReceipt(
            job_id=job.job_id,
            provider=recommended,
            status=ProviderDryRunStatus.DRY_RUN,
            reason=None,
            model_hint=profile.model_hint,
            prompt_length_chars=len(job.prompt),
            aspect_ratio=job.aspect_ratio,
            dimensions_px=job.dimensions_px,
            simulated_output_filename=job.output_filename_suggestion,
            notes=(
                "Dry-run only. No request was issued; the request "
                "shape above is what a future provider-integration "
                "block would send."
            ),
        )


def build_and_persist_provider_plan(
    memory: Memory, *, client_slug: str,
) -> ImageProviderRecommendationPack:
    planner = ImageProviderPlanner(memory=memory)
    pack = planner.plan(client_slug)
    planner.persist(pack)
    return pack


# ---------- scoring helpers ----------


def _weighted_score(profile: ImageProviderProfile, piece_type: str) -> float:
    overlay = _PIECE_TYPE_WEIGHT_OVERLAYS.get(piece_type, {})
    total = 0.0
    for criterion in PROVIDER_CRITERIA:
        weight = _BASE_WEIGHTS.get(criterion, 0.0)
        weight += overlay.get(criterion, 0.0)
        score = profile.score_of(criterion)
        total += weight * score
    return total


def _provider_supports_aspect(
    profile: ImageProviderProfile, aspect_ratio: str,
) -> bool:
    if "any" in profile.supported_aspect_ratios:
        return True
    return aspect_ratio in profile.supported_aspect_ratios


def _build_rationale(
    *,
    recommended: str,
    score: float,
    job: ImageGenerationJob,
    profile: ImageProviderProfile,
) -> str:
    parts: list[str] = []
    if recommended == "manual":
        parts.append(
            f"Manual designer chosen — no provider scored ≥ {_FALLBACK_SCORE_FLOOR}."
        )
    elif recommended == job.provider_suggestion.value:
        parts.append(
            f"Agrees with job hint `{job.provider_suggestion.value}` "
            f"(score {score:.2f})."
        )
    else:
        parts.append(
            f"Overrides job hint `{job.provider_suggestion.value}` "
            f"with `{recommended}` (score {score:.2f})."
        )
    parts.append(
        f"Integration difficulty: {profile.integration_difficulty}; "
        f"external dependency risk: {profile.external_dependency_risk}."
    )
    if profile.notes:
        parts.append(profile.notes)
    return " ".join(parts)


def _build_risk_notes(
    *,
    recommended: str,
    profile: ImageProviderProfile,
    job: ImageGenerationJob,
) -> list[str]:
    notes: list[str] = []
    if recommended != "manual":
        if profile.score_of("artifact_risk") <= 2:
            notes.append(
                "Elevated artifact risk — reviewer must zoom in on "
                "typography + faces."
            )
        if profile.score_of("commercial_use") <= 3:
            notes.append(
                "Commercial-use posture varies — confirm the model's "
                "license before launch."
            )
        if profile.score_of("external_dependency") <= 2:
            notes.append(
                "High external dependency — single point of failure if "
                "the provider changes pricing / TOS / availability."
            )
        if profile.credentials_required:
            notes.append(
                "Credentials required: "
                + ", ".join(profile.credentials_required)
                + " (NOT read in MKT-7B — set them only when the "
                "real-integration block ships)."
            )
    if job.in_image_text:
        notes.append(
            "Job has in-image text — proof-read the output before delivery."
        )
    return notes


def _build_stats(
    *,
    recommendations: list[ImageProviderRecommendation],
    receipts: list[ProviderDryRunReceipt],
    overrode_job_suggestion: int,
    skipped_blocked: int,
    skipped_manual: int,
    total_cost: float,
) -> ImageProviderRecommendationStats:
    by_provider: dict[str, int] = {}
    for r in recommendations:
        by_provider[r.recommended_provider] = (
            by_provider.get(r.recommended_provider, 0) + 1
        )
    by_status: dict[str, int] = {}
    for r in receipts:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
    return ImageProviderRecommendationStats(
        total_jobs=len(recommendations),
        by_recommended_provider=by_provider,
        by_dry_run_status=by_status,
        overrode_job_suggestion=overrode_job_suggestion,
        skipped_blocked=skipped_blocked,
        skipped_manual=skipped_manual,
        total_estimated_cost_usd=round(total_cost, 4),
    )


__all__ = [
    "DEFAULT_PROVIDER_PLANNER_RULE_SET_ID",
    "ImageProviderPlanner",
    "build_and_persist_provider_plan",
]
