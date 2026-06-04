"""Tests for the Image Generation Job Pack models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.image_jobs.models import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    IMAGE_GENERATION_JOB_PACK_VERSION,
    ImageGenerationJob,
    ImageGenerationJobPack,
    ImageJobReviewChecklistItem,
    ImageJobState,
    ImageJobStats,
    ImageProviderSuggestion,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _base_pack(**overrides) -> dict:
    base = dict(
        client_slug="acme",
        visual_pack_id="vp-1",
        visual_pack_contract_version="visual-direction-pack.v1",
        jobs=[],
        review_checklist=[],
        stats=ImageJobStats(
            total_jobs=0, by_state={}, by_provider_suggestion={},
            by_piece_type={}, directions_consumed=0,
            blocked_due_to_approval=0, blocked_due_to_direction=0,
        ),
        created_at=_now(),
    )
    base.update(overrides)
    return base


def _base_job(**overrides) -> dict:
    base = dict(
        piece_type="instagram_post",
        channel="instagram",
        direction_id="dir-1",
        variant_id="v1",
        prompt="A bright square poster.",
        negative_prompt="blurry, low quality, watermark",
        aspect_ratio="1:1",
        dimensions_px="1080x1080",
        output_filename_suggestion="acme--instagram_post--v1.png",
        provider_suggestion=ImageProviderSuggestion.REPLICATE,
        state=ImageJobState.DRAFT,
    )
    base.update(overrides)
    return base


def test_kind_constants() -> None:
    assert IMAGE_GENERATION_JOB_PACK_KIND == "image_generation_job_pack"
    assert IMAGE_GENERATION_JOB_PACK_VERSION == "image-generation-job-pack.v1"


def test_pack_round_trip() -> None:
    pack = ImageGenerationJobPack(**_base_pack())
    raw = pack.model_dump(mode="json")
    again = ImageGenerationJobPack.model_validate(raw)
    assert again.pack_id == pack.pack_id
    assert again.contract_version == IMAGE_GENERATION_JOB_PACK_VERSION


def test_pack_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ImageGenerationJobPack(**_base_pack(created_at=datetime(2026, 6, 4)))


def test_pack_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError):
        ImageGenerationJobPack(**_base_pack(client_slug="UPPER"))


def test_job_state_enum_complete() -> None:
    expected = {
        "draft", "needs_review", "blocked",
        "ready_for_generation", "generated",
    }
    assert {s.value for s in ImageJobState} == expected


def test_provider_enum_complete() -> None:
    expected = {
        "openai_images", "replicate", "midjourney", "stability_ai",
        "canva", "figma", "manual",
    }
    assert {p.value for p in ImageProviderSuggestion} == expected


def test_job_round_trip() -> None:
    j = ImageGenerationJob(**_base_job())
    raw = j.model_dump(mode="json")
    again = ImageGenerationJob.model_validate(raw)
    assert again.job_id == j.job_id


def test_job_can_deserialize_generated_state() -> None:
    """``GENERATED`` is reserved — a future block can write it.
    Deserialisation must accept it for round-trip even though the
    factory never emits it today."""
    j = ImageGenerationJob(**_base_job(state=ImageJobState.GENERATED))
    raw = j.model_dump(mode="json")
    again = ImageGenerationJob.model_validate(raw)
    assert again.state is ImageJobState.GENERATED


def test_no_credential_fields_on_job() -> None:
    forbidden = {
        "token", "api_key", "secret", "credential", "url",
        "webhook_url", "provider_account_id",
    }
    declared = set(ImageGenerationJob.model_fields.keys())
    assert declared.isdisjoint(forbidden), declared & forbidden


def test_no_credential_fields_on_pack() -> None:
    forbidden = {
        "token", "api_key", "secret", "credential", "url",
        "webhook_url",
    }
    declared = set(ImageGenerationJobPack.model_fields.keys())
    assert declared.isdisjoint(forbidden), declared & forbidden


def test_extra_fields_forbidden_on_pack() -> None:
    with pytest.raises(ValueError):
        ImageGenerationJobPack(**_base_pack(secret_token="nope"))


def test_review_checklist_severity_default_info() -> None:
    item = ImageJobReviewChecklistItem(title="Check")
    assert item.severity == "info"
