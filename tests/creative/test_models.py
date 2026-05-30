"""Pydantic validation tests for creative pack models."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from core.creative import (
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
from core.domain.enums import ChannelType


def _now() -> datetime:
    return datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _minimal_pack(**overrides) -> dict:
    base = {
        "contract_version": CREATIVE_PACK_VERSION,
        "pack_id": "p1",
        "client_slug": "demo-saas",
        "report_id": "r1",
        "report_contract_version": "campaign-strategy.v1",
        "approval_pack_id": None,
        "approval_pack_contract_version": None,
        "derived_overall_state": "draft",
        "blocks_publish": False,
        "social_posts": [],
        "emails": [],
        "reels": [],
        "flyers": [],
        "image_prompts": [],
        "calendar": [],
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
        "rule_set_id": "default-templates.v1",
    }
    base.update(overrides)
    return base


# ---------- CreativeAssetPack ----------

def test_minimal_pack_validates() -> None:
    pack = CreativeAssetPack.model_validate(_minimal_pack())
    assert pack.contract_version == CREATIVE_PACK_VERSION
    assert pack.total_assets == 0


def test_pack_round_trip_json() -> None:
    pack = CreativeAssetPack.model_validate(_minimal_pack())
    reloaded = CreativeAssetPack.from_json(pack.to_json())
    assert reloaded.model_dump() == pack.model_dump()


def test_pack_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        CreativeAssetPack.model_validate(
            _minimal_pack(created_at="2026-05-30T12:00:00")
        )


def test_pack_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        CreativeAssetPack.model_validate(_minimal_pack(client_slug="Bad Slug"))


def test_pack_version_pinned() -> None:
    with pytest.raises(ValidationError):
        CreativeAssetPack.model_validate(
            _minimal_pack(contract_version="creative-pack.v2")
        )


def test_pack_extra_field_rejected() -> None:
    data = _minimal_pack()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        CreativeAssetPack.model_validate(data)


# ---------- counts ----------

def test_count_by_state_with_assets() -> None:
    social = SocialPostAsset(
        channel=ChannelType.LINKEDIN,
        hook_variants=[HookVariant(variant_id="A", text="x", angle=VariantAngle.CURIOSITY)],
        body="body",
        cta_variants=[CTAVariant(variant_id="A", text="go", style=CTAStyle.DIRECT)],
        state=CreativeAssetState.NEEDS_REVIEW,
    )
    pack = CreativeAssetPack.model_validate(
        _minimal_pack(social_posts=[social.model_dump(mode="json")])
    )
    counts = pack.count_by_state()
    assert counts["needs_review"] == 1
    assert pack.total_assets == 1


def test_count_by_kind() -> None:
    email = EmailAsset(
        step=1,
        subject_line_variants=[
            SubjectLineVariant(
                variant_id="A",
                subject="s",
                preview_text="p",
                style=SubjectStyle.DIRECT,
            )
        ],
        body="b",
        cta="c",
        send_after_days=0,
    )
    pack = CreativeAssetPack.model_validate(
        _minimal_pack(emails=[email.model_dump(mode="json")])
    )
    counts = pack.count_by_kind()
    assert counts["email"] == 1
    assert counts["social_post"] == 0


# ---------- per-asset bounds ----------

def test_social_requires_at_least_one_hook() -> None:
    with pytest.raises(ValidationError):
        SocialPostAsset(
            channel=ChannelType.LINKEDIN,
            hook_variants=[],
            body="b",
            cta_variants=[CTAVariant(variant_id="A", text="x", style=CTAStyle.DIRECT)],
        )


def test_social_requires_at_least_one_cta() -> None:
    with pytest.raises(ValidationError):
        SocialPostAsset(
            channel=ChannelType.LINKEDIN,
            hook_variants=[HookVariant(variant_id="A", text="x", angle=VariantAngle.CURIOSITY)],
            body="b",
            cta_variants=[],
        )


def test_email_step_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        EmailAsset(
            step=0,
            subject_line_variants=[
                SubjectLineVariant(
                    variant_id="A",
                    subject="s",
                    preview_text="p",
                    style=SubjectStyle.DIRECT,
                )
            ],
            body="b",
            cta="c",
            send_after_days=0,
        )


def test_subject_max_length() -> None:
    with pytest.raises(ValidationError):
        SubjectLineVariant(
            variant_id="A",
            subject="x" * 81,
            preview_text="p",
            style=SubjectStyle.DIRECT,
        )


def test_reels_duration_bounds() -> None:
    with pytest.raises(ValidationError):
        ReelsAsset(
            title="t",
            hook_variants=[HookVariant(variant_id="A", text="x", angle=VariantAngle.CURIOSITY)],
            beats=["x"],
            cta="c",
            target_duration_s=999,
        )


def test_flyer_format_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        FlyerAsset(
            format="custom",  # type: ignore[arg-type]
            headline_variants=[
                HeadlineVariant(variant_id="A", text="x", style=HeadlineStyle.BENEFIT)
            ],
            subhead="s",
            body="b",
            cta="c",
        )


def test_image_prompt_default_state_is_draft() -> None:
    a = ImagePromptAsset(
        title="t",
        intended_use="hero",
        prompt_text="prompt",
        aspect_ratio="16:9",
    )
    assert a.state is CreativeAssetState.DRAFT


# ---------- variants / checklist ----------

def test_checklist_severity_enum() -> None:
    with pytest.raises(ValidationError):
        AssetChecklistItem(title="x", severity="meh")  # type: ignore[arg-type]


def test_hook_angle_enforced() -> None:
    with pytest.raises(ValidationError):
        HookVariant(variant_id="A", text="x", angle="vibes")  # type: ignore[arg-type]


def test_flyer_format_values_are_aspect_strings() -> None:
    assert FlyerFormat.SQUARE.value == "1:1"
    assert FlyerFormat.PORTRAIT_4_5.value == "4:5"
    assert FlyerFormat.STORY_9_16.value == "9:16"


# ---------- calendar entry ----------

def test_calendar_entry_week_bounds() -> None:
    from core.creative import CalendarEntry, CreativeAssetKind

    with pytest.raises(ValidationError):
        CalendarEntry(
            asset_id="a",
            asset_kind=CreativeAssetKind.SOCIAL_POST,
            week=0,
            scheduled_for=date(2026, 6, 1),
        )
