"""Static provider profiles + criteria — MKT-7B.

Module-level constants only. NO HTTP. NO SDK import. NO
credential read. The numbers and notes encode the user's
intuition about each provider at the time of writing; they are
intentionally coarse (per-tenant overrides are P-7B.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Criteria the user listed in the MKT-7B spec.
PROVIDER_CRITERIA: tuple[str, ...] = (
    "expected_quality",
    "cost",
    "api_support",
    "format_aspect_support",
    "integration_ease",
    "security",
    "style_control",
    "artifact_risk",
    "commercial_use",
    "external_dependency",
)


@dataclass(frozen=True)
class ProviderCriterion:
    """Per-criterion score + free-form note."""

    score: int  # 0..5
    note: str = ""


@dataclass(frozen=True)
class ImageProviderProfile:
    """Static profile for one provider — scores + meta facts."""

    provider: str
    estimated_cost_usd_per_image: float
    commercial_use_ok: bool
    credentials_required: tuple[str, ...]
    supported_aspect_ratios: tuple[str, ...]
    supported_formats: tuple[str, ...]
    integration_difficulty: str  # "low" / "medium" / "high"
    external_dependency_risk: str  # "low" / "medium" / "high"
    model_hint: str
    notes: str
    scores: dict[str, ProviderCriterion] = field(default_factory=dict)

    def score_of(self, criterion: str) -> int:
        c = self.scores.get(criterion)
        return c.score if c is not None else 0


# ---------- per-provider profiles ----------


def _profile_openai_images() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="openai_images",
        estimated_cost_usd_per_image=0.08,
        commercial_use_ok=True,
        credentials_required=("OPENAI_API_KEY",),
        supported_aspect_ratios=("1:1", "16:9", "9:16", "3:2", "2:3"),
        supported_formats=("png", "webp"),
        integration_difficulty="low",
        external_dependency_risk="medium",
        model_hint="dall-e-3",
        notes=(
            "Single official SDK; quality bar is high for hero / "
            "landing pieces. Style control limited vs. Midjourney."
        ),
        scores={
            "expected_quality": ProviderCriterion(4, "Strong hero output."),
            "cost": ProviderCriterion(3, "Per-image price typical."),
            "api_support": ProviderCriterion(5, "Mature SDK + docs."),
            "format_aspect_support": ProviderCriterion(4),
            "integration_ease": ProviderCriterion(5),
            "security": ProviderCriterion(4, "TOS + content filter."),
            "style_control": ProviderCriterion(3),
            "artifact_risk": ProviderCriterion(3),
            "commercial_use": ProviderCriterion(5),
            "external_dependency": ProviderCriterion(3, "Single vendor."),
        },
    )


def _profile_replicate() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="replicate",
        estimated_cost_usd_per_image=0.012,
        commercial_use_ok=True,
        credentials_required=("REPLICATE_API_TOKEN",),
        supported_aspect_ratios=(
            "1:1", "16:9", "9:16", "4:5", "5:4", "3:2", "2:3", "21:9",
        ),
        supported_formats=("png", "webp", "jpg"),
        integration_difficulty="low",
        external_dependency_risk="medium",
        model_hint="black-forest-labs/flux-schnell",
        notes=(
            "Many community models — fast iteration for social, but "
            "requires per-model checklist for commercial use."
        ),
        scores={
            "expected_quality": ProviderCriterion(4),
            "cost": ProviderCriterion(5, "Cheap per image."),
            "api_support": ProviderCriterion(4),
            "format_aspect_support": ProviderCriterion(5),
            "integration_ease": ProviderCriterion(5),
            "security": ProviderCriterion(3),
            "style_control": ProviderCriterion(4),
            "artifact_risk": ProviderCriterion(3),
            "commercial_use": ProviderCriterion(3, "Per-model varies."),
            "external_dependency": ProviderCriterion(2, "Many hosted models."),
        },
    )


def _profile_stability_ai() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="stability_ai",
        estimated_cost_usd_per_image=0.03,
        commercial_use_ok=True,
        credentials_required=("STABILITY_API_KEY",),
        supported_aspect_ratios=("1:1", "16:9", "9:16", "3:2", "2:3", "5:4"),
        supported_formats=("png", "webp", "jpg"),
        integration_difficulty="medium",
        external_dependency_risk="medium",
        model_hint="stable-image-ultra",
        notes=(
            "Fallback when other providers refuse the prompt. "
            "Quality slightly behind hero providers."
        ),
        scores={
            "expected_quality": ProviderCriterion(3),
            "cost": ProviderCriterion(4),
            "api_support": ProviderCriterion(3),
            "format_aspect_support": ProviderCriterion(4),
            "integration_ease": ProviderCriterion(3),
            "security": ProviderCriterion(3),
            "style_control": ProviderCriterion(3),
            "artifact_risk": ProviderCriterion(2),
            "commercial_use": ProviderCriterion(5),
            "external_dependency": ProviderCriterion(3),
        },
    )


def _profile_midjourney() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="midjourney",
        estimated_cost_usd_per_image=0.05,
        commercial_use_ok=True,
        credentials_required=("MIDJOURNEY_TOKEN",),
        supported_aspect_ratios=(
            "1:1", "16:9", "9:16", "4:5", "5:4", "3:2", "2:3",
        ),
        supported_formats=("png", "webp", "jpg"),
        integration_difficulty="high",
        external_dependency_risk="high",
        model_hint="midjourney-v7",
        notes=(
            "Best style control + typography-heavy pieces. NO "
            "official API today — third-party brokers required, "
            "elevated TOS / dependency risk."
        ),
        scores={
            "expected_quality": ProviderCriterion(5),
            "cost": ProviderCriterion(3),
            "api_support": ProviderCriterion(2, "No official API."),
            "format_aspect_support": ProviderCriterion(4),
            "integration_ease": ProviderCriterion(2),
            "security": ProviderCriterion(3),
            "style_control": ProviderCriterion(5),
            "artifact_risk": ProviderCriterion(3),
            "commercial_use": ProviderCriterion(4),
            "external_dependency": ProviderCriterion(1, "Third-party broker."),
        },
    )


def _profile_canva() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="canva",
        estimated_cost_usd_per_image=0.02,
        commercial_use_ok=True,
        credentials_required=("CANVA_API_TOKEN",),
        supported_aspect_ratios=("1:1", "16:9", "9:16", "4:5", "5:4"),
        supported_formats=("png", "jpg", "pdf"),
        integration_difficulty="medium",
        external_dependency_risk="medium",
        model_hint="canva-templates-v1",
        notes=(
            "Best for brand-template pieces — keeps the agency "
            "template intact. Limited free-form generation."
        ),
        scores={
            "expected_quality": ProviderCriterion(3),
            "cost": ProviderCriterion(4),
            "api_support": ProviderCriterion(3),
            "format_aspect_support": ProviderCriterion(4),
            "integration_ease": ProviderCriterion(3),
            "security": ProviderCriterion(4),
            "style_control": ProviderCriterion(5, "Templates lock style."),
            "artifact_risk": ProviderCriterion(5, "Template = no artifacts."),
            "commercial_use": ProviderCriterion(5),
            "external_dependency": ProviderCriterion(3),
        },
    )


def _profile_figma() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="figma",
        estimated_cost_usd_per_image=0.0,
        commercial_use_ok=True,
        credentials_required=("FIGMA_API_TOKEN",),
        supported_aspect_ratios=("any",),
        supported_formats=("png", "jpg", "svg", "pdf"),
        integration_difficulty="high",
        external_dependency_risk="low",
        model_hint="figma-export",
        notes=(
            "Designer composes manually — Figma export only. No "
            "AI generation. Highest fidelity, slowest throughput."
        ),
        scores={
            "expected_quality": ProviderCriterion(5),
            "cost": ProviderCriterion(2, "Designer time, not API cost."),
            "api_support": ProviderCriterion(3, "Export API only."),
            "format_aspect_support": ProviderCriterion(5),
            "integration_ease": ProviderCriterion(2),
            "security": ProviderCriterion(5),
            "style_control": ProviderCriterion(5),
            "artifact_risk": ProviderCriterion(5),
            "commercial_use": ProviderCriterion(5),
            "external_dependency": ProviderCriterion(4),
        },
    )


def _profile_manual() -> ImageProviderProfile:
    return ImageProviderProfile(
        provider="manual",
        estimated_cost_usd_per_image=0.0,
        commercial_use_ok=True,
        credentials_required=(),
        supported_aspect_ratios=("any",),
        supported_formats=("png", "jpg", "webp", "svg", "pdf"),
        integration_difficulty="low",
        external_dependency_risk="low",
        model_hint="agency-designer",
        notes=(
            "Agency designer composes by hand. Always-safe fallback "
            "when no provider scores well enough."
        ),
        scores={
            "expected_quality": ProviderCriterion(5),
            "cost": ProviderCriterion(1, "Designer time is expensive."),
            "api_support": ProviderCriterion(0, "No API."),
            "format_aspect_support": ProviderCriterion(5),
            "integration_ease": ProviderCriterion(5),
            "security": ProviderCriterion(5),
            "style_control": ProviderCriterion(5),
            "artifact_risk": ProviderCriterion(5),
            "commercial_use": ProviderCriterion(5),
            "external_dependency": ProviderCriterion(5, "No external dep."),
        },
    )


DEFAULT_PROVIDER_PROFILES: dict[str, ImageProviderProfile] = {
    p.provider: p
    for p in (
        _profile_openai_images(),
        _profile_replicate(),
        _profile_stability_ai(),
        _profile_midjourney(),
        _profile_canva(),
        _profile_figma(),
        _profile_manual(),
    )
}


__all__ = [
    "DEFAULT_PROVIDER_PROFILES",
    "ImageProviderProfile",
    "PROVIDER_CRITERIA",
    "ProviderCriterion",
]
