"""Tests for the MKT-7B Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.image_provider_plan.models import (
    IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND,
    IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION,
    ImageProviderRecommendation,
    ImageProviderRecommendationPack,
    ImageProviderRecommendationStats,
    ProviderCriterionScore,
    ProviderDryRunReceipt,
    ProviderDryRunStatus,
    ProviderEvaluation,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _stats() -> ImageProviderRecommendationStats:
    return ImageProviderRecommendationStats(
        total_jobs=0, by_recommended_provider={}, by_dry_run_status={},
        overrode_job_suggestion=0, skipped_blocked=0, skipped_manual=0,
        total_estimated_cost_usd=0.0,
    )


def _base_pack(**overrides) -> dict:
    base = dict(
        client_slug="acme",
        job_pack_id="ijp-1",
        job_pack_contract_version="image-generation-job-pack.v1",
        evaluations=[],
        recommendations=[],
        dry_run_receipts=[],
        stats=_stats(),
        created_at=_now(),
    )
    base.update(overrides)
    return base


def test_kind_constants() -> None:
    assert IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND == (
        "image_provider_recommendation_pack"
    )
    assert IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION == (
        "image-provider-recommendation-pack.v1"
    )


def test_pack_round_trip() -> None:
    pack = ImageProviderRecommendationPack(**_base_pack())
    raw = pack.model_dump(mode="json")
    again = ImageProviderRecommendationPack.model_validate(raw)
    assert again.pack_id == pack.pack_id


def test_pack_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ImageProviderRecommendationPack(
            **_base_pack(created_at=datetime(2026, 6, 4)),
        )


def test_pack_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError):
        ImageProviderRecommendationPack(**_base_pack(client_slug="UPPER"))


def test_dry_run_status_enum_values() -> None:
    assert {s.value for s in ProviderDryRunStatus} == {
        "dry_run", "skipped_blocked", "skipped_manual",
    }


def test_criterion_score_bounds() -> None:
    with pytest.raises(ValueError):
        ProviderCriterionScore(criterion="x", score=6)
    with pytest.raises(ValueError):
        ProviderCriterionScore(criterion="x", score=-1)


def test_recommendation_round_trip() -> None:
    rec = ImageProviderRecommendation(
        job_id="j1",
        piece_type="landing_hero",
        job_state="ready_for_generation",
        job_provider_suggestion="openai_images",
        recommended_provider="openai_images",
        recommended_score=25.5,
        alternative_providers=["replicate"],
        fallback_provider="manual",
        rationale="ok",
        risk_notes=[],
        estimated_cost_usd=0.08,
    )
    raw = rec.model_dump(mode="json")
    again = ImageProviderRecommendation.model_validate(raw)
    assert again.recommended_provider == "openai_images"


def test_receipt_round_trip() -> None:
    r = ProviderDryRunReceipt(
        job_id="j1",
        provider="openai_images",
        status=ProviderDryRunStatus.DRY_RUN,
        model_hint="dall-e-3",
        prompt_length_chars=120,
        aspect_ratio="1:1",
        dimensions_px="1080x1080",
        simulated_output_filename="acme--landing_hero--v1.png",
    )
    raw = r.model_dump(mode="json")
    again = ProviderDryRunReceipt.model_validate(raw)
    assert again.status is ProviderDryRunStatus.DRY_RUN


def test_no_credential_fields_on_receipt() -> None:
    forbidden = {
        "token", "api_key", "secret", "credential", "url", "webhook_url",
    }
    fields = set(ProviderDryRunReceipt.model_fields.keys())
    assert fields.isdisjoint(forbidden), fields & forbidden


def test_no_credential_fields_on_recommendation() -> None:
    forbidden = {"token", "api_key", "secret", "credential", "url"}
    fields = set(ImageProviderRecommendation.model_fields.keys())
    assert fields.isdisjoint(forbidden), fields & forbidden


def test_no_credential_fields_on_pack() -> None:
    forbidden = {"token", "api_key", "secret", "credential", "url"}
    fields = set(ImageProviderRecommendationPack.model_fields.keys())
    assert fields.isdisjoint(forbidden), fields & forbidden


def test_evaluation_carries_credentials_required_as_strings() -> None:
    ev = ProviderEvaluation(
        provider="openai_images",
        estimated_cost_usd_per_image=0.08,
        commercial_use_ok=True,
        credentials_required=["OPENAI_API_KEY"],
        integration_difficulty="low",
        external_dependency_risk="medium",
    )
    # Field is a list of plain names — not values.
    assert ev.credentials_required == ["OPENAI_API_KEY"]
