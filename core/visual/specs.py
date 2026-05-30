"""Per-piece-type visual specifications (dimensions, safe zones, file format).

These are static, channel-aware specifications. The factory consumes them
to populate every :class:`PieceVisualDirection`. Same input → same specs;
no I/O, no LLM, no external lookups.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from core.domain.base import DomainModel
from core.domain.enums import ChannelType


class PieceType(StrEnum):
    """11 piece types supported by the visual direction pack."""

    INSTAGRAM_POST = "instagram_post"
    INSTAGRAM_STORY = "instagram_story"
    INSTAGRAM_CAROUSEL = "instagram_carousel"
    LINKEDIN_POST_GRAPHIC = "linkedin_post_graphic"
    FACEBOOK_POST = "facebook_post"
    REELS_COVER = "reels_cover"
    EMAIL_HEADER = "email_header"
    LANDING_HERO = "landing_hero"
    AD_CREATIVE = "ad_creative"
    FLYER_SQUARE = "flyer_square"
    FLYER_VERTICAL = "flyer_vertical"


class PieceTypeSpec(DomainModel):
    """Static specification for one piece type."""

    piece_type: PieceType
    channel: ChannelType | None = None
    aspect_ratio: str = Field(min_length=1, max_length=64)
    dimensions_px: str = Field(min_length=1, max_length=80)
    file_format_hints: list[str] = Field(default_factory=list)
    safe_zones: dict[str, str] = Field(default_factory=dict)
    text_guidelines: dict[str, str] = Field(default_factory=dict)
    delivery_notes: list[str] = Field(default_factory=list)
    typical_negative_prompt: str = Field(min_length=1)


# ---------- Default spec catalogue ----------

# One spec per :class:`PieceType`. Adding a new piece type requires adding
# an entry here.

DEFAULT_PIECE_SPECS: dict[PieceType, PieceTypeSpec] = {
    PieceType.INSTAGRAM_POST: PieceTypeSpec(
        piece_type=PieceType.INSTAGRAM_POST,
        channel=ChannelType.INSTAGRAM,
        aspect_ratio="1:1",
        dimensions_px="1080×1080",
        file_format_hints=["PNG", "JPG @ 85%"],
        safe_zones={
            "top": "100 px (avoid status bar overlap)",
            "bottom": "100 px (avoid UI overlap)",
            "sides": "60 px",
        },
        text_guidelines={
            "max_chars_overlay": "60",
            "min_font_size_px": "32",
            "contrast": "AA against background",
        },
        delivery_notes=[
            "Centrar el sujeto en el cuadrado.",
            "Mantener color saturado dentro del rango brand.",
        ],
        typical_negative_prompt=(
            "no busy backgrounds, no watermarks, no low resolution, "
            "no stock handshakes, no purple gradient backgrounds, "
            "no clip-art icons, no obvious AI artifacts"
        ),
    ),
    PieceType.INSTAGRAM_STORY: PieceTypeSpec(
        piece_type=PieceType.INSTAGRAM_STORY,
        channel=ChannelType.INSTAGRAM,
        aspect_ratio="9:16",
        dimensions_px="1080×1920",
        file_format_hints=["MP4 (Reels)", "PNG (Static)"],
        safe_zones={
            "top": "220 px (profile + actions area)",
            "bottom": "220 px (reply + send bar)",
            "sides": "60 px",
        },
        text_guidelines={
            "max_chars_overlay": "40",
            "min_font_size_px": "48",
            "max_lines": "3",
        },
        delivery_notes=[
            "Texto importante dentro del safe zone central (1080×1480).",
            "Hook visual en los primeros 1.5s si es video.",
        ],
        typical_negative_prompt=(
            "no cropped faces near edges, no important text in the bottom 200px, "
            "no flat low-contrast palettes, no watermarks"
        ),
    ),
    PieceType.INSTAGRAM_CAROUSEL: PieceTypeSpec(
        piece_type=PieceType.INSTAGRAM_CAROUSEL,
        channel=ChannelType.INSTAGRAM,
        aspect_ratio="1:1",
        dimensions_px="1080×1080 (per slide, 3-7 slides)",
        file_format_hints=["PNG / JPG per slide"],
        safe_zones={
            "top": "100 px",
            "bottom": "150 px (swipe-cue zone)",
            "sides": "60 px",
        },
        text_guidelines={
            "max_chars_per_slide": "70",
            "min_font_size_px": "36",
            "slide_count_range": "3-7",
        },
        delivery_notes=[
            "Cada slide debe poder leerse sola.",
            "Mantener un sistema visual consistente entre slides.",
        ],
        typical_negative_prompt=(
            "no inconsistent slide layouts, no varying type sizes, "
            "no missing slide numbers, no off-brand colors"
        ),
    ),
    PieceType.LINKEDIN_POST_GRAPHIC: PieceTypeSpec(
        piece_type=PieceType.LINKEDIN_POST_GRAPHIC,
        channel=ChannelType.LINKEDIN,
        aspect_ratio="1.91:1",
        dimensions_px="1200×628",
        file_format_hints=["PNG", "JPG @ 90%"],
        safe_zones={
            "top": "60 px",
            "bottom": "60 px",
            "sides": "80 px",
        },
        text_guidelines={
            "max_chars_overlay": "80",
            "min_font_size_px": "28",
            "tone": "professional, not playful",
        },
        delivery_notes=[
            "Composición editorial; menos es más en LinkedIn.",
            "Evitar memes y cliché corporativo.",
        ],
        typical_negative_prompt=(
            "no handshake stock photos, no group around-a-table shots, "
            "no purple/teal corporate gradients, no jargon-heavy overlays"
        ),
    ),
    PieceType.FACEBOOK_POST: PieceTypeSpec(
        piece_type=PieceType.FACEBOOK_POST,
        channel=ChannelType.FACEBOOK,
        aspect_ratio="1.91:1",
        dimensions_px="1200×628",
        file_format_hints=["PNG", "JPG @ 85%"],
        safe_zones={
            "top": "60 px",
            "bottom": "60 px",
            "sides": "80 px",
        },
        text_guidelines={
            "text_over_image_pct_max": "20%",
            "min_font_size_px": "28",
        },
        delivery_notes=[
            "Texto sobre imagen no más del 20% del área (recomendación FB).",
            "Hook visual claro para feed scroll.",
        ],
        typical_negative_prompt=(
            "no excessive text overlay, no QR codes covering subject, "
            "no busy clutter, no low-contrast color schemes"
        ),
    ),
    PieceType.REELS_COVER: PieceTypeSpec(
        piece_type=PieceType.REELS_COVER,
        channel=ChannelType.TIKTOK,
        aspect_ratio="9:16",
        dimensions_px="1080×1920",
        file_format_hints=["JPG cover frame", "MP4 source"],
        safe_zones={
            "top": "250 px",
            "bottom": "300 px (caption area)",
            "sides": "80 px",
        },
        text_guidelines={
            "title_max_chars": "30",
            "min_font_size_px": "56",
        },
        delivery_notes=[
            "Frame de cover debe legible aún sin contexto.",
            "Cara o objeto en zona central; texto top-third.",
        ],
        typical_negative_prompt=(
            "no flat 2D illustrations as covers, no tiny title text, "
            "no overlap with TikTok UI zones, no inconsistent typography"
        ),
    ),
    PieceType.EMAIL_HEADER: PieceTypeSpec(
        piece_type=PieceType.EMAIL_HEADER,
        channel=ChannelType.EMAIL,
        aspect_ratio="3:1",
        dimensions_px="600×200",
        file_format_hints=["PNG", "JPG @ 80%"],
        safe_zones={
            "top": "20 px",
            "bottom": "20 px",
            "sides": "40 px",
        },
        text_guidelines={
            "max_overlay_chars": "30",
            "min_font_size_px": "24",
            "alt_text_required": "yes",
        },
        delivery_notes=[
            "Subir alt text descriptivo (accesibilidad).",
            "Mantener carga <100KB para inboxes lentos.",
        ],
        typical_negative_prompt=(
            "no large file sizes, no missing alt text, "
            "no complex images that fail dark-mode rendering"
        ),
    ),
    PieceType.LANDING_HERO: PieceTypeSpec(
        piece_type=PieceType.LANDING_HERO,
        channel=None,
        aspect_ratio="16:9",
        dimensions_px="1920×1080",
        file_format_hints=["WebP", "JPG @ 85%"],
        safe_zones={
            "top": "120 px",
            "bottom": "120 px",
            "sides": "200 px",
        },
        text_guidelines={
            "headline_overlay_chars": "60",
            "min_font_size_desktop_px": "48",
            "responsive_breakpoint_notes": "ensure mobile crop preserves subject",
        },
        delivery_notes=[
            "Zona negativa para overlay de headline + CTA.",
            "Optimizar para mobile (60% del tráfico esperado).",
        ],
        typical_negative_prompt=(
            "no busy backgrounds where headline goes, no low-contrast subjects, "
            "no stock-cliché office workers, no AI artifact hands"
        ),
    ),
    PieceType.AD_CREATIVE: PieceTypeSpec(
        piece_type=PieceType.AD_CREATIVE,
        channel=ChannelType.PAID_SOCIAL,
        aspect_ratio="multiple (1:1, 9:16, 1.91:1)",
        dimensions_px="1080×1080 / 1080×1920 / 1200×628",
        file_format_hints=["PNG", "JPG @ 85%", "MP4 if motion"],
        safe_zones={
            "top": "100 px",
            "bottom": "150 px",
            "sides": "80 px",
        },
        text_guidelines={
            "text_over_image_pct_max": "20%",
            "min_font_size_px": "32",
            "cta_required": "yes",
        },
        delivery_notes=[
            "Entregar al menos 3 ratios (1:1, 9:16, 1.91:1).",
            "CTA visible en TODOS los formats.",
        ],
        typical_negative_prompt=(
            "no misleading claims, no fake UI mockups, "
            "no countdown timers without verification, "
            "no copy that violates platform ad policies"
        ),
    ),
    PieceType.FLYER_SQUARE: PieceTypeSpec(
        piece_type=PieceType.FLYER_SQUARE,
        channel=None,
        aspect_ratio="1:1",
        dimensions_px="1080×1080",
        file_format_hints=["PNG", "PDF if print"],
        safe_zones={
            "margin": "80 px",
        },
        text_guidelines={
            "headline_max_chars": "50",
            "min_font_size_px": "32",
        },
        delivery_notes=[
            "Si imprime, exportar también a PDF 300dpi.",
            "Tipografía dominante > imagen dominante.",
        ],
        typical_negative_prompt=(
            "no cluttered layouts, no decorative fonts, "
            "no missing CTA, no off-brand color combinations"
        ),
    ),
    PieceType.FLYER_VERTICAL: PieceTypeSpec(
        piece_type=PieceType.FLYER_VERTICAL,
        channel=None,
        aspect_ratio="4:5",
        dimensions_px="1080×1350",
        file_format_hints=["PNG", "PDF if print"],
        safe_zones={
            "margin": "80 px",
        },
        text_guidelines={
            "headline_max_chars": "60",
            "min_font_size_px": "32",
        },
        delivery_notes=[
            "Apto para Stories y para impreso A4-ish.",
            "Jerarquía visual: headline → subhead → body → CTA.",
        ],
        typical_negative_prompt=(
            "no stock photos with watermarks, no overuse of gradients, "
            "no missing breathing room around copy"
        ),
    ),
}


def get_spec(piece_type: PieceType) -> PieceTypeSpec:
    """Return the catalogue spec for a piece type."""
    return DEFAULT_PIECE_SPECS[piece_type]


def all_piece_types() -> list[PieceType]:
    """Stable order across the catalogue (matches enum declaration order)."""
    return list(PieceType)


__all__ = [
    "PieceType",
    "PieceTypeSpec",
    "DEFAULT_PIECE_SPECS",
    "get_spec",
    "all_piece_types",
]
