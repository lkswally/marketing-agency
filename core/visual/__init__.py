"""Visual Direction & Image Prompt Pack (MKT-3D).

Contract: ``visual-direction-pack.v1``.

The factory consumes a :class:`CampaignStrategyReport` (MKT-3A) and
optionally an :class:`ApprovalPack` (MKT-3B) + :class:`CreativeAssetPack`
(MKT-3C), and produces a deterministic :class:`VisualDirectionPack` with
11 piece-type specifications, A/B prompt variants per piece, a
campaign-wide style guide, visual risks and a checklist.

No image is generated. No external API is called. The pack is 100% text.
"""

from __future__ import annotations

from .models import (
    VISUAL_DIRECTION_PACK_VERSION,
    PieceVisualDirection,
    VisualChecklistItem,
    VisualDirectionPack,
    VisualPromptVariant,
    VisualRisk,
    VisualStyleGuide,
)
from .prompt_factory import (
    DEFAULT_RULE_SET_ID,
    SINGLETON_ID,
    VISUAL_PACK_KIND,
    VisualPromptFactory,
    build_and_persist,
)
from .renderer import render_markdown_pack
from .specs import (
    DEFAULT_PIECE_SPECS,
    PieceType,
    PieceTypeSpec,
    all_piece_types,
    get_spec,
)

__all__ = [
    "VISUAL_DIRECTION_PACK_VERSION",
    "VISUAL_PACK_KIND",
    "SINGLETON_ID",
    "DEFAULT_RULE_SET_ID",
    # Factory
    "VisualPromptFactory",
    "build_and_persist",
    # Renderer
    "render_markdown_pack",
    # Top-level
    "VisualDirectionPack",
    "VisualStyleGuide",
    "PieceVisualDirection",
    "VisualPromptVariant",
    "VisualChecklistItem",
    "VisualRisk",
    # Specs
    "PieceType",
    "PieceTypeSpec",
    "DEFAULT_PIECE_SPECS",
    "get_spec",
    "all_piece_types",
]
