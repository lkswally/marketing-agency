"""Pydantic validation tests for visual direction pack models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.creative.models import CreativeAssetState
from core.visual import (
    VISUAL_DIRECTION_PACK_VERSION,
    PieceVisualDirection,
    VisualChecklistItem,
    VisualDirectionPack,
    VisualPromptVariant,
    VisualRisk,
    VisualStyleGuide,
    get_spec,
)
from core.visual.specs import PieceType


def _now() -> datetime:
    return datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _good_style_guide() -> VisualStyleGuide:
    return VisualStyleGuide(
        palette_primary=["#000000"],
        typography_headline="Sans",
        typography_body="Sans",
        overall_mood="editorial",
    )


def _good_variant(variant_id="A") -> VisualPromptVariant:
    return VisualPromptVariant(
        variant_id=variant_id,
        objective="x",
        target_audience="y",
        visual_style="z",
        emotional_tone="w",
        composition="c",
        in_image_text=[],
        visual_elements=[],
        suggested_colors=[],
        aspect_ratio="1:1",
        restrictions=[],
        negative_prompt="no",
        intended_use="ig",
        full_prompt_text="full",
    )


def _minimal_pack(**overrides) -> dict:
    direction = PieceVisualDirection(
        piece_type=PieceType.INSTAGRAM_POST,
        channel=None,
        spec=get_spec(PieceType.INSTAGRAM_POST),
        prompt_variants=[_good_variant()],
        state=CreativeAssetState.DRAFT,
    )
    base = {
        "contract_version": VISUAL_DIRECTION_PACK_VERSION,
        "pack_id": "p1",
        "client_slug": "demo-saas",
        "report_id": "r1",
        "report_contract_version": "campaign-strategy.v1",
        "approval_pack_id": None,
        "approval_pack_contract_version": None,
        "creative_pack_id": None,
        "creative_pack_contract_version": None,
        "derived_overall_state": "draft",
        "blocks_publish": False,
        "style_guide": _good_style_guide().model_dump(mode="json"),
        "directions": [direction.model_dump(mode="json")],
        "global_visual_risks": [],
        "global_checklist": [],
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
        "rule_set_id": "default-visual-rules.v1",
    }
    base.update(overrides)
    return base


# ---------- VisualDirectionPack ----------

def test_minimal_pack_validates() -> None:
    pack = VisualDirectionPack.model_validate(_minimal_pack())
    assert pack.contract_version == VISUAL_DIRECTION_PACK_VERSION
    assert pack.total_directions == 1


def test_pack_round_trip_json() -> None:
    pack = VisualDirectionPack.model_validate(_minimal_pack())
    reloaded = VisualDirectionPack.from_json(pack.to_json())
    assert reloaded.model_dump() == pack.model_dump()


def test_pack_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        VisualDirectionPack.model_validate(
            _minimal_pack(created_at="2026-05-30T12:00:00")
        )


def test_pack_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        VisualDirectionPack.model_validate(_minimal_pack(client_slug="Bad Slug"))


def test_pack_version_pinned() -> None:
    with pytest.raises(ValidationError):
        VisualDirectionPack.model_validate(
            _minimal_pack(contract_version="visual-direction-pack.v2")
        )


def test_pack_extra_field_rejected() -> None:
    data = _minimal_pack()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        VisualDirectionPack.model_validate(data)


# ---------- counts ----------

def test_total_prompt_variants_aggregates() -> None:
    direction = PieceVisualDirection(
        piece_type=PieceType.INSTAGRAM_POST,
        spec=get_spec(PieceType.INSTAGRAM_POST),
        prompt_variants=[_good_variant("A"), _good_variant("B")],
    )
    pack = VisualDirectionPack.model_validate(
        _minimal_pack(directions=[direction.model_dump(mode="json")])
    )
    assert pack.total_prompt_variants == 2


def test_count_by_state() -> None:
    needs = PieceVisualDirection(
        piece_type=PieceType.INSTAGRAM_POST,
        spec=get_spec(PieceType.INSTAGRAM_POST),
        prompt_variants=[_good_variant()],
        state=CreativeAssetState.NEEDS_REVIEW,
    )
    pack = VisualDirectionPack.model_validate(
        _minimal_pack(directions=[needs.model_dump(mode="json")])
    )
    counts = pack.count_by_state()
    assert counts["needs_review"] == 1
    assert counts["draft"] == 0


def test_count_risks_by_severity() -> None:
    risks = [
        VisualRisk(category="stock_cliche", severity="high", description="x").model_dump(mode="json"),
        VisualRisk(category="accessibility", severity="high", description="y").model_dump(mode="json"),
        VisualRisk(category="ai_artifacts", severity="medium", description="z").model_dump(mode="json"),
    ]
    pack = VisualDirectionPack.model_validate(_minimal_pack(global_visual_risks=risks))
    counts = pack.count_risks_by_severity()
    assert counts["high"] == 2
    assert counts["medium"] == 1
    assert counts["low"] == 0


# ---------- VisualPromptVariant ----------

def test_variant_requires_all_12_fields() -> None:
    with pytest.raises(ValidationError):
        VisualPromptVariant(
            variant_id="A",
            objective="x",
            target_audience="y",
            visual_style="z",
            emotional_tone="w",
            composition="c",
            in_image_text=[],
            visual_elements=[],
            suggested_colors=[],
            aspect_ratio="1:1",
            restrictions=[],
            negative_prompt="",
            intended_use="ig",
            full_prompt_text="full",
        )


def test_variant_long_aspect_ratio_accepted() -> None:
    # The "multiple (1:1, 9:16, 1.91:1)" string must fit in the field.
    v = _good_variant()
    v_dump = v.model_dump(mode="json")
    v_dump["aspect_ratio"] = "multiple (1:1, 9:16, 1.91:1)"
    VisualPromptVariant.model_validate(v_dump)


# ---------- VisualChecklistItem ----------

def test_checklist_severity_enum() -> None:
    with pytest.raises(ValidationError):
        VisualChecklistItem(title="x", severity="meh", category="brand")  # type: ignore[arg-type]


def test_checklist_category_enum() -> None:
    with pytest.raises(ValidationError):
        VisualChecklistItem(
            title="x", severity="must", category="random"  # type: ignore[arg-type]
        )


# ---------- VisualRisk ----------

def test_risk_severity_enum() -> None:
    with pytest.raises(ValidationError):
        VisualRisk(category="stock_cliche", severity="critical", description="x")  # type: ignore[arg-type]


def test_risk_category_enum() -> None:
    with pytest.raises(ValidationError):
        VisualRisk(category="random", severity="medium", description="x")  # type: ignore[arg-type]


# ---------- PieceVisualDirection ----------

def test_direction_requires_at_least_one_variant() -> None:
    with pytest.raises(ValidationError):
        PieceVisualDirection(
            piece_type=PieceType.INSTAGRAM_POST,
            spec=get_spec(PieceType.INSTAGRAM_POST),
            prompt_variants=[],
        )


def test_direction_caps_at_four_variants() -> None:
    with pytest.raises(ValidationError):
        PieceVisualDirection(
            piece_type=PieceType.INSTAGRAM_POST,
            spec=get_spec(PieceType.INSTAGRAM_POST),
            prompt_variants=[_good_variant(str(i)) for i in range(5)],
        )
