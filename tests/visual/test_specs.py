"""Tests for the per-piece-type specifications catalogue."""

from __future__ import annotations

from core.domain.enums import ChannelType
from core.visual import all_piece_types, get_spec
from core.visual.specs import DEFAULT_PIECE_SPECS, PieceType


def test_catalogue_has_eleven_piece_types() -> None:
    assert len(DEFAULT_PIECE_SPECS) == 11


def test_all_piece_types_returns_enum_order() -> None:
    pts = all_piece_types()
    assert pts == list(PieceType)
    assert len(pts) == 11


def test_every_piece_type_has_spec() -> None:
    for pt in PieceType:
        spec = get_spec(pt)
        assert spec.piece_type is pt
        assert spec.aspect_ratio
        assert spec.dimensions_px
        assert spec.typical_negative_prompt


def test_instagram_specs_use_instagram_channel() -> None:
    for pt in (
        PieceType.INSTAGRAM_POST,
        PieceType.INSTAGRAM_STORY,
        PieceType.INSTAGRAM_CAROUSEL,
    ):
        assert get_spec(pt).channel is ChannelType.INSTAGRAM


def test_linkedin_spec_uses_linkedin_channel() -> None:
    assert get_spec(PieceType.LINKEDIN_POST_GRAPHIC).channel is ChannelType.LINKEDIN


def test_facebook_spec_uses_facebook_channel() -> None:
    assert get_spec(PieceType.FACEBOOK_POST).channel is ChannelType.FACEBOOK


def test_email_header_uses_email_channel() -> None:
    assert get_spec(PieceType.EMAIL_HEADER).channel is ChannelType.EMAIL


def test_landing_and_flyer_specs_have_no_channel() -> None:
    assert get_spec(PieceType.LANDING_HERO).channel is None
    assert get_spec(PieceType.FLYER_SQUARE).channel is None
    assert get_spec(PieceType.FLYER_VERTICAL).channel is None


def test_ad_creative_supports_multiple_ratios() -> None:
    spec = get_spec(PieceType.AD_CREATIVE)
    assert "multiple" in spec.aspect_ratio.lower() or "," in spec.aspect_ratio


def test_each_spec_has_typical_negative_prompt() -> None:
    for pt in PieceType:
        assert get_spec(pt).typical_negative_prompt


def test_aspect_ratios_are_canonical_strings() -> None:
    expected = {
        PieceType.INSTAGRAM_POST: "1:1",
        PieceType.INSTAGRAM_STORY: "9:16",
        PieceType.INSTAGRAM_CAROUSEL: "1:1",
        PieceType.LINKEDIN_POST_GRAPHIC: "1.91:1",
        PieceType.FACEBOOK_POST: "1.91:1",
        PieceType.REELS_COVER: "9:16",
        PieceType.EMAIL_HEADER: "3:1",
        PieceType.LANDING_HERO: "16:9",
        PieceType.FLYER_SQUARE: "1:1",
        PieceType.FLYER_VERTICAL: "4:5",
    }
    for pt, ratio in expected.items():
        assert get_spec(pt).aspect_ratio == ratio
