"""Tests for the MKT-7B Markdown renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from core.image_provider_plan import (
    ImageProviderRecommendation,
    ImageProviderRecommendationPack,
    ImageProviderRecommendationStats,
    ProviderCriterionScore,
    ProviderDryRunReceipt,
    ProviderDryRunStatus,
    render_markdown_provider_plan,
)
from core.image_provider_plan.models import ProviderEvaluation


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _make_pack(**overrides) -> ImageProviderRecommendationPack:
    recs = overrides.pop("recommendations", [])
    receipts = overrides.pop("dry_run_receipts", [])
    evals = overrides.pop("evaluations", [])
    stats = ImageProviderRecommendationStats(
        total_jobs=len(recs),
        by_recommended_provider={r.recommended_provider: 1 for r in recs},
        by_dry_run_status={r.status.value: 1 for r in receipts},
        overrode_job_suggestion=overrides.pop("overrode_job_suggestion", 0),
        skipped_blocked=overrides.pop("skipped_blocked", 0),
        skipped_manual=overrides.pop("skipped_manual", 0),
        total_estimated_cost_usd=overrides.pop("total_cost", 0.0),
    )
    return ImageProviderRecommendationPack(
        client_slug="acme",
        job_pack_id="ijp-1",
        job_pack_contract_version="image-generation-job-pack.v1",
        evaluations=evals,
        recommendations=recs,
        dry_run_receipts=receipts,
        stats=stats,
        created_at=_now(),
        rule_set_id="image-provider-planner.v1",
    )


def test_render_empty_pack() -> None:
    md = render_markdown_provider_plan(_make_pack())
    assert "Image Provider Plan" in md
    assert "no jobs to recommend" in md
    assert "Pure analysis + dry-run preview" in md


def test_render_includes_evaluation_table() -> None:
    ev = ProviderEvaluation(
        provider="openai_images",
        scores=[ProviderCriterionScore(criterion="expected_quality", score=4)],
        estimated_cost_usd_per_image=0.08,
        commercial_use_ok=True,
        credentials_required=["OPENAI_API_KEY"],
        supported_aspect_ratios=["1:1"],
        supported_formats=["png"],
        integration_difficulty="low",
        external_dependency_risk="medium",
    )
    md = render_markdown_provider_plan(_make_pack(evaluations=[ev]))
    assert "openai_images" in md
    assert "OPENAI_API_KEY" in md
    assert "| expected_quality | 4 |" in md


def test_render_includes_recommendation() -> None:
    rec = ImageProviderRecommendation(
        job_id="j1",
        piece_type="landing_hero",
        job_state="ready_for_generation",
        job_provider_suggestion="openai_images",
        recommended_provider="openai_images",
        recommended_score=27.5,
        alternative_providers=["replicate"],
        rationale="Hero piece — quality wins.",
        risk_notes=["Confirm license."],
        estimated_cost_usd=0.08,
    )
    md = render_markdown_provider_plan(_make_pack(recommendations=[rec]))
    assert "openai_images" in md
    assert "Confirm license." in md
    assert "$0.0800" in md


def test_render_dry_run_receipt() -> None:
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
    md = render_markdown_provider_plan(_make_pack(dry_run_receipts=[r]))
    assert "[DRY-RUN]" in md
    assert "dall-e-3" in md


def test_render_skipped_receipt() -> None:
    r = ProviderDryRunReceipt(
        job_id="j1",
        provider="openai_images",
        status=ProviderDryRunStatus.SKIPPED_BLOCKED,
        reason="Approval pack blocks publish.",
        model_hint="dall-e-3",
        prompt_length_chars=120,
        aspect_ratio="1:1",
        dimensions_px="1080x1080",
        simulated_output_filename="acme--landing_hero--v1.png",
    )
    md = render_markdown_provider_plan(_make_pack(dry_run_receipts=[r]))
    assert "[SKIPPED (blocked)]" in md
    assert "Approval pack" in md


def test_renderer_is_pure() -> None:
    pack = _make_pack()
    assert render_markdown_provider_plan(pack) == render_markdown_provider_plan(pack)
