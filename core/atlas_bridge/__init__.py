"""ATLAS Bridge Contract (MKT-8A).

Defines the structured handoff briefs MARKETING-AGENCY-OS emits
when a campaign asset requires work that belongs to a separate
web / branding / design system — historically ATLAS.

Contracts:

- ``landing-brief.v1`` — :class:`LandingBrief`
- ``branding-brief.v1`` — :class:`BrandingBrief`
- ``page-design-brief.v1`` — :class:`PageDesignBrief`
- ``atlas-handoff-brief.v1`` — :class:`AtlasHandoffBrief` —
  envelope that wraps one of the three.

**No code in this module reaches into ATLAS.** No HTTP. No
shared filesystem. No imports from ATLAS. The handoff is a
plain Markdown + JSON deliverable an operator copies / pastes
into whatever ATLAS workflow they use today.
"""

from __future__ import annotations

from .factory import (
    DEFAULT_ATLAS_BRIDGE_RULE_SET_ID,
    AtlasHandoffFactory,
    build_and_persist_atlas_handoff,
)
from .models import (
    ATLAS_HANDOFF_BRIEF_KIND,
    ATLAS_HANDOFF_BRIEF_VERSION,
    BRANDING_BRIEF_VERSION,
    LANDING_BRIEF_VERSION,
    PAGE_DESIGN_BRIEF_VERSION,
    SINGLETON_ID,
    AtlasHandoffBrief,
    AtlasHandoffKind,
    BrandingBrief,
    BrandingTokenSet,
    HandoffAssetReference,
    LandingBrief,
    LandingSection,
    PageDesignBlock,
    PageDesignBrief,
    SEOGEOTargets,
)
from .renderer import render_markdown_atlas_handoff

__all__ = [
    "ATLAS_HANDOFF_BRIEF_KIND",
    "ATLAS_HANDOFF_BRIEF_VERSION",
    "AtlasHandoffBrief",
    "AtlasHandoffFactory",
    "AtlasHandoffKind",
    "BRANDING_BRIEF_VERSION",
    "BrandingBrief",
    "BrandingTokenSet",
    "DEFAULT_ATLAS_BRIDGE_RULE_SET_ID",
    "HandoffAssetReference",
    "LANDING_BRIEF_VERSION",
    "LandingBrief",
    "LandingSection",
    "PAGE_DESIGN_BRIEF_VERSION",
    "PageDesignBlock",
    "PageDesignBrief",
    "SEOGEOTargets",
    "SINGLETON_ID",
    "build_and_persist_atlas_handoff",
    "render_markdown_atlas_handoff",
]
