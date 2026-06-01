"""TemplatedStrategyBackend — pure wrapper around ``core.strategy.templates``.

Always succeeds. Never falls back (it IS the fallback). Output is
byte-identical to MKT-3A behavior — this backend is the "safe path"
and exists so the orchestrator has one canonical content provider
that never depends on anything external.
"""

from __future__ import annotations

from .. import templates
from ..models import (
    CampaignStrategy,
    CreativeBriefPack,
    EmailSequenceDraft,
    ReelsScriptPack,
    SocialPostDraft,
    StrategyInputBrief,
    TargetAudience,
    ValueProposition,
)
from .base import BackendKind, StrategyBackend


class TemplatedStrategyBackend(StrategyBackend):
    """Deterministic content backend. The default for ``mkt run-campaign``."""

    kind = BackendKind.TEMPLATED

    def value_proposition(
        self,
        brief: StrategyInputBrief,
        audience: TargetAudience,
    ) -> ValueProposition:
        return templates.generate_value_proposition(brief, audience)

    def campaign_strategy(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
    ) -> CampaignStrategy:
        return templates.generate_campaign_strategy(brief, value_prop)

    def creative_brief_pack(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> CreativeBriefPack:
        return templates.generate_creative_brief_pack(brief, value_prop, audience)

    def social_post_drafts(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        channels,
        keyword_plan,
    ) -> list[SocialPostDraft]:
        return templates.generate_social_post_drafts(
            brief, value_prop, channels, keyword_plan
        )

    def email_sequence(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> EmailSequenceDraft:
        return templates.generate_email_sequence(brief, value_prop, audience)

    def reels_script_pack(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> ReelsScriptPack:
        return templates.generate_reels_script_pack(brief, value_prop, audience)


__all__ = ["TemplatedStrategyBackend"]
