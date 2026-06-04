"""Tests for the image jobs Markdown renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from core.image_jobs import (
    ImageGenerationJob,
    ImageGenerationJobPack,
    ImageJobReviewChecklistItem,
    ImageJobState,
    ImageJobStats,
    ImageProviderSuggestion,
    render_markdown_image_jobs,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _make_pack(**overrides) -> ImageGenerationJobPack:
    jobs = overrides.pop("jobs", [])
    checklist = overrides.pop("review_checklist", [])
    stats = ImageJobStats(
        total_jobs=len(jobs),
        by_state={s.value: 1 for s in {j.state for j in jobs}},
        by_provider_suggestion={
            j.provider_suggestion.value: 1 for j in jobs
        },
        by_piece_type={j.piece_type: 1 for j in jobs},
        directions_consumed=overrides.pop("directions_consumed", 1),
        blocked_due_to_approval=overrides.pop("blocked_due_to_approval", 0),
        blocked_due_to_direction=overrides.pop("blocked_due_to_direction", 0),
    )
    return ImageGenerationJobPack(
        client_slug="acme",
        visual_pack_id="vp-1",
        visual_pack_contract_version="visual-direction-pack.v1",
        jobs=jobs,
        review_checklist=checklist,
        stats=stats,
        blocks_publish=overrides.pop("blocks_publish", False),
        created_at=_now(),
        rule_set_id="image-job-factory.v1",
    )


def _make_job(**overrides) -> ImageGenerationJob:
    base = dict(
        piece_type="instagram_post",
        channel="instagram",
        direction_id="dir-1",
        variant_id="v1",
        prompt="A bright square poster.",
        negative_prompt="blurry, low quality",
        aspect_ratio="1:1",
        dimensions_px="1080x1080",
        output_filename_suggestion="acme--instagram_post--v1.png",
        provider_suggestion=ImageProviderSuggestion.REPLICATE,
        state=ImageJobState.DRAFT,
    )
    base.update(overrides)
    return ImageGenerationJob(**base)


def test_render_empty_pack() -> None:
    md = render_markdown_image_jobs(_make_pack())
    assert "Image Generation Jobs" in md
    assert "no jobs" in md
    assert "No provider was called" in md


def test_render_one_job() -> None:
    job = _make_job()
    md = render_markdown_image_jobs(_make_pack(jobs=[job]))
    assert "instagram_post" in md
    assert "Aspect ratio" in md
    assert "1080x1080" in md
    assert "Provider suggestion" in md
    assert "replicate" in md
    assert "A bright square poster." in md


def test_render_blocked_job_shows_blocker() -> None:
    job = _make_job(
        state=ImageJobState.BLOCKED,
        blocked_reason="Approval pack blocks publish.",
        review_checklist=[ImageJobReviewChecklistItem(
            title="Resolve approval before generating.",
            severity="blocker",
        )],
    )
    md = render_markdown_image_jobs(_make_pack(jobs=[job]))
    assert "[BLOCKED]" in md
    assert "[BLOCKER]" in md
    assert "Approval pack blocks publish." in md


def test_renderer_is_pure() -> None:
    pack = _make_pack(jobs=[_make_job()])
    assert render_markdown_image_jobs(pack) == render_markdown_image_jobs(pack)
