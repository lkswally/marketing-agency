"""AtlasHandoffFactory — assemble a handoff brief from persisted packs.

Reads upstream campaign packs from Memory and emits one of:

- :class:`LandingBrief` wrapped in :class:`AtlasHandoffBrief`
- :class:`BrandingBrief` wrapped in :class:`AtlasHandoffBrief`
- :class:`PageDesignBrief` wrapped in :class:`AtlasHandoffBrief`

depending on the caller's ``kind`` argument.

**No network call. No ATLAS reach-in. No write outside the
client memory namespace.** The handoff is a plain JSON +
Markdown artifact the operator copies / pastes into whatever
ATLAS workflow they use.
"""

from __future__ import annotations

import contextlib

from core.approval import APPROVAL_PACK_KIND, ApprovalPack
from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.domain.base import utcnow
from core.image_jobs.models import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    ImageGenerationJobPack,
)
from core.image_jobs.models import (
    SINGLETON_ID as JOB_PACK_SINGLETON,
)
from core.memory import EntityNotFound, Memory
from core.strategy import REPORT_KIND, CampaignStrategyReport
from core.strategy import SINGLETON_ID as STRATEGY_SINGLETON
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

from .models import (
    ATLAS_HANDOFF_BRIEF_KIND,
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

DEFAULT_ATLAS_BRIDGE_RULE_SET_ID = "atlas-bridge.v1"


class AtlasHandoffFactory:
    """Stateful factory over a Memory."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # ---------- public ----------

    def build(
        self,
        *,
        client_slug: str,
        kind: AtlasHandoffKind,
        page_name: str | None = None,
    ) -> AtlasHandoffBrief:
        strategy = self._load_strategy(client_slug)
        approval = self._optional_load(
            client_slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON, ApprovalPack,
        )
        creative = self._optional_load(
            client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON, CreativeAssetPack,
        )
        visual = self._optional_load(
            client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON, VisualDirectionPack,
        )
        job_pack = self._optional_load(
            client_slug, IMAGE_GENERATION_JOB_PACK_KIND, JOB_PACK_SINGLETON,
            ImageGenerationJobPack,
        )

        landing = None
        branding = None
        page_design = None
        if kind is AtlasHandoffKind.LANDING:
            landing = _build_landing_brief(
                strategy=strategy, creative=creative, visual=visual,
                job_pack=job_pack,
            )
        elif kind is AtlasHandoffKind.BRANDING:
            branding = _build_branding_brief(
                strategy=strategy, visual=visual,
            )
        else:
            page_design = _build_page_design_brief(
                strategy=strategy, creative=creative, visual=visual,
                job_pack=job_pack, page_name=page_name or "about",
            )

        blocks_publish = bool(
            getattr(approval, "blocks_publish", False)
            or getattr(visual, "blocks_publish", False)
        )

        return AtlasHandoffBrief(
            client_slug=client_slug,
            kind=kind,
            landing_brief=landing,
            branding_brief=branding,
            page_design_brief=page_design,
            strategy_report_id=getattr(strategy, "report_id", None),
            creative_pack_id=getattr(creative, "pack_id", None),
            visual_pack_id=getattr(visual, "pack_id", None),
            approval_pack_id=getattr(approval, "pack_id", None),
            image_job_pack_id=getattr(job_pack, "pack_id", None),
            blocks_publish=blocks_publish,
            created_at=utcnow(),
            rule_set_id=DEFAULT_ATLAS_BRIDGE_RULE_SET_ID,
        )

    def persist(self, handoff: AtlasHandoffBrief) -> None:
        # MKT-9B: persist per-kind so emitting landing then branding
        # then page_design does NOT overwrite the previous brief. The
        # singleton id is the kind value (``"landing"`` /
        # ``"branding"`` / ``"page_design"``). The legacy
        # ``"current"`` singleton is also written so the most-recent
        # write remains easy to find (matches MKT-8A behaviour for
        # backward compat with anything that reads ``current.json``
        # by name).
        payload = handoff.model_dump(mode="json")
        self._memory.put(
            handoff.client_slug,
            ATLAS_HANDOFF_BRIEF_KIND,
            handoff.kind.value,
            payload,
        )
        self._memory.put(
            handoff.client_slug,
            ATLAS_HANDOFF_BRIEF_KIND,
            SINGLETON_ID,
            payload,
        )
        prev = self._memory.last_audit_hash(handoff.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="atlas_handoff_factory",
            occurred_at=utcnow(),
            client_slug=handoff.client_slug,
            payload={
                "atlas_handoff_brief": {
                    "action": "built",
                    "handoff_id": handoff.handoff_id,
                    "kind": handoff.kind.value,
                    "strategy_report_id": handoff.strategy_report_id,
                    "creative_pack_id": handoff.creative_pack_id,
                    "visual_pack_id": handoff.visual_pack_id,
                    "blocks_publish": handoff.blocks_publish,
                    "rule_set_id": handoff.rule_set_id,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    # ---------- internals ----------

    def _load_strategy(self, client_slug: str) -> CampaignStrategyReport:
        try:
            raw = self._memory.get(
                client_slug, REPORT_KIND, STRATEGY_SINGLETON,
            )
        except EntityNotFound as e:
            raise ValueError(
                f"no CampaignStrategyReport for client {client_slug!r} — "
                "run `mkt run-strategy` (or `mkt run-campaign`) first."
            ) from e
        return CampaignStrategyReport.model_validate(raw)

    def _optional_load(
        self, client_slug: str, kind: str, singleton: str, cls,
    ):
        with contextlib.suppress(EntityNotFound):
            return cls.model_validate(
                self._memory.get(client_slug, kind, singleton),
            )
        return None


def build_and_persist_atlas_handoff(
    memory: Memory,
    *,
    client_slug: str,
    kind: AtlasHandoffKind,
    page_name: str | None = None,
) -> AtlasHandoffBrief:
    factory = AtlasHandoffFactory(memory=memory)
    handoff = factory.build(
        client_slug=client_slug, kind=kind, page_name=page_name,
    )
    factory.persist(handoff)
    return handoff


# ---------- per-kind builders ----------


def _build_landing_brief(
    *,
    strategy: CampaignStrategyReport,
    creative: CreativeAssetPack | None,
    visual: VisualDirectionPack | None,
    job_pack: ImageGenerationJobPack | None,
) -> LandingBrief:
    target_audience = _audience_text(strategy)
    visual_style = _visual_style_text(visual)
    primary_cta = _primary_cta(creative) or "Solicitar demo"
    sections = _default_landing_sections(
        strategy=strategy, creative=creative, job_pack=job_pack,
    )
    seo = _seo_targets(strategy)
    return LandingBrief(
        page_objective=(
            f"Landing page to support the campaign "
            f"`{strategy.client_slug}` — drive {primary_cta.lower()} "
            "as the primary conversion."
        ),
        target_audience=target_audience,
        primary_cta_label=primary_cta,
        secondary_cta_label=None,
        sections=sections,
        visual_style_notes=visual_style,
        reference_links=[],
        seo_geo=seo,
        constraints=[
            "Respect the upstream approval pack — do not ship while "
            "`blocks_publish=True` on the source packs.",
            "Do not invent claims not present in the strategy report "
            "or approved creative.",
        ],
        acceptance_criteria=[
            "Hero copy matches the approved creative verbatim.",
            "Primary CTA label matches the approved CTA.",
            "Mobile + desktop layouts validated against the visual "
            "style notes.",
            "SEO title + meta description respect the provided hints.",
            "No external assets are inlined — only references the "
            "agency provides.",
        ],
    )


def _build_branding_brief(
    *,
    strategy: CampaignStrategyReport,
    visual: VisualDirectionPack | None,
) -> BrandingBrief:
    audience = _audience_text(strategy)
    positioning = _positioning_text(strategy)
    tokens = _branding_tokens(visual)
    return BrandingBrief(
        brand_objective=(
            f"Establish a coherent visual identity for "
            f"`{strategy.client_slug}` aligned with the current "
            "campaign positioning."
        ),
        target_audience=audience,
        positioning_statement=positioning,
        competitor_landscape=None,
        tokens=tokens,
        deliverables_requested=[
            "logo_primary",
            "logo_compact",
            "color_palette",
            "typography_system",
            "brand_voice_guide",
        ],
        reference_links=[],
        constraints=[
            "Inherit the campaign visual tone from the visual pack "
            "when present.",
            "Do not introduce colours or fonts that contradict the "
            "approved creative.",
        ],
        acceptance_criteria=[
            "Logo works on light + dark + monochrome backgrounds.",
            "Palette passes WCAG AA contrast for body text.",
            "Typography system covers display + body + UI scales.",
            "Voice guide produces 3 sample microcopy pieces matching "
            "the campaign tone.",
        ],
    )


def _build_page_design_brief(
    *,
    strategy: CampaignStrategyReport,
    creative: CreativeAssetPack | None,
    visual: VisualDirectionPack | None,
    job_pack: ImageGenerationJobPack | None,
    page_name: str,
) -> PageDesignBrief:
    audience = _audience_text(strategy)
    visual_style = _visual_style_text(visual)
    blocks = [
        PageDesignBlock(
            name="intro",
            intent=f"Introduce the `{page_name}` page in 2-3 sentences.",
            body_copy=(
                f"Bienvenido a {page_name}. "
                + (strategy.executive_summary.headline or "")
            )[:500] or "Intro copy pending — see strategy report.",
            visual_notes=None,
        ),
        PageDesignBlock(
            name="value_proposition",
            intent="State the value proposition for the visitor.",
            body_copy=_value_prop_text(strategy),
        ),
        PageDesignBlock(
            name="proof",
            intent="Provide proof (case studies, testimonials, data).",
            body_copy=_proof_text(strategy),
            assets=_assets_from_packs(creative, job_pack)[:4],
        ),
        PageDesignBlock(
            name="cta",
            intent="Close with a clear next-step CTA.",
            body_copy=_primary_cta(creative) or "Solicitar demo",
        ),
    ]
    return PageDesignBrief(
        page_name=page_name,
        page_objective=(
            f"Generic `{page_name}` page supporting the campaign — "
            "informational, not directly conversion-driven."
        ),
        target_audience=audience,
        blocks=blocks,
        visual_style_notes=visual_style,
        reference_links=[],
        seo_geo=_seo_targets(strategy),
        constraints=[
            "Respect the upstream approval pack.",
            "Do not introduce content beyond what the strategy "
            "report and creative pack approve.",
        ],
        acceptance_criteria=[
            "Each block has a clear heading and supporting copy.",
            "Visual style matches the upstream visual pack.",
            "SEO hints respected.",
        ],
    )


# ---------- text helpers ----------


def _audience_text(strategy: CampaignStrategyReport) -> str:
    """Pull a free-form audience description from the strategy
    report. The strategy schema may evolve — we probe defensively
    via ``model_dump`` so a missing field never crashes the
    factory."""

    raw = strategy.model_dump()
    target = raw.get("target_audience") or {}
    parts: list[str] = []
    if isinstance(target, dict):
        label = target.get("label")
        if label:
            parts.append(str(label))
        pain = target.get("pain_points") or []
        if isinstance(pain, list) and pain:
            parts.append("Pain points: " + ", ".join(str(p) for p in pain[:3]))
        outcomes = target.get("desired_outcomes") or []
        if isinstance(outcomes, list) and outcomes:
            parts.append(
                "Desired outcomes: " + ", ".join(str(o) for o in outcomes[:3])
            )
    if parts:
        return " | ".join(parts)[:400]
    return "Target audience TBD — clarify with account lead."


def _visual_style_text(visual: VisualDirectionPack | None) -> str:
    if visual is None:
        return (
            "No visual direction pack available. Use a clean, modern "
            "layout aligned with the campaign tone."
        )
    style = visual.style_guide
    parts: list[str] = []
    if style.palette_primary:
        parts.append(f"Primary palette: {', '.join(style.palette_primary)}")
    if style.palette_accent:
        parts.append(f"Accent palette: {', '.join(style.palette_accent)}")
    if style.composition_principles:
        parts.append(
            "Composition: " + "; ".join(style.composition_principles[:5])
        )
    if style.do_use:
        parts.append("Do use: " + "; ".join(style.do_use[:5]))
    if style.do_not_use:
        parts.append("Do NOT use: " + "; ".join(style.do_not_use[:5]))
    if not parts:
        parts.append(
            "Visual pack present but minimal — request style guide expansion."
        )
    return " | ".join(parts)[:2000]


def _branding_tokens(visual: VisualDirectionPack | None) -> BrandingTokenSet:
    if visual is None:
        return BrandingTokenSet()
    sg = visual.style_guide
    return BrandingTokenSet(
        palette_primary=list(sg.palette_primary),
        palette_accent=list(sg.palette_accent),
        typography_principles=list(sg.typography_principles),
        voice_tone_principles=[],
        logo_usage_principles=[],
        do_use=list(sg.do_use),
        do_not_use=list(sg.do_not_use),
    )


def _primary_cta(creative: CreativeAssetPack | None) -> str | None:
    if creative is None:
        return None
    raw = creative.model_dump()
    for asset in raw.get("assets", []):
        cta = asset.get("cta_label") or asset.get("primary_cta")
        if cta:
            return str(cta)[:64]
    return None


def _positioning_text(strategy: CampaignStrategyReport) -> str:
    raw = strategy.model_dump()
    vp = raw.get("value_proposition") or {}
    if isinstance(vp, dict):
        headline = vp.get("headline")
        if headline:
            return str(headline)[:600]
    exec_summary = raw.get("executive_summary") or {}
    headline = exec_summary.get("headline") if isinstance(exec_summary, dict) else None
    return str(headline)[:600] if headline else (
        "Positioning TBD — clarify with account lead."
    )


def _value_prop_text(strategy: CampaignStrategyReport) -> str:
    raw = strategy.model_dump()
    vp = raw.get("value_proposition") or {}
    if isinstance(vp, dict):
        parts: list[str] = []
        if vp.get("headline"):
            parts.append(str(vp["headline"]))
        if vp.get("primary_benefit"):
            parts.append(str(vp["primary_benefit"]))
        diffs = vp.get("differentiators") or []
        if isinstance(diffs, list) and diffs:
            parts.append("Differentiators: " + ", ".join(
                str(d) for d in diffs[:5]
            ))
        if parts:
            return " | ".join(parts)[:1000]
    exec_summary = raw.get("executive_summary") or {}
    headline = exec_summary.get("headline") if isinstance(exec_summary, dict) else None
    return str(headline)[:1000] if headline else (
        "Value proposition TBD — see strategy report."
    )


def _proof_text(strategy: CampaignStrategyReport) -> str:
    raw = strategy.model_dump()
    vp = raw.get("value_proposition") or {}
    if isinstance(vp, dict):
        proof = vp.get("proof_points") or []
        if isinstance(proof, list) and proof:
            return " | ".join(str(p) for p in proof[:5])[:1500]
    diag = raw.get("diagnosis") or {}
    if isinstance(diag, dict):
        strengths = diag.get("strengths") or []
        if isinstance(strengths, list) and strengths:
            return "Strengths: " + ", ".join(
                str(s) for s in strengths[:5]
            )
    return "Proof points TBD — list case studies / testimonials."


def _seo_targets(strategy: CampaignStrategyReport) -> SEOGEOTargets:
    raw = strategy.model_dump()
    kp = raw.get("keyword_plan") or {}
    primary = None
    secondary: list[str] = []
    if isinstance(kp, dict):
        primary_list = kp.get("primary_keywords") or []
        secondary_list = kp.get("secondary_keywords") or []
        if isinstance(primary_list, list) and primary_list:
            primary = str(_keyword_text(primary_list[0]))
            secondary.extend(
                str(_keyword_text(k)) for k in primary_list[1:]
            )
        if isinstance(secondary_list, list):
            secondary.extend(
                str(_keyword_text(k)) for k in secondary_list
            )
    return SEOGEOTargets(
        primary_keyword=primary,
        secondary_keywords=[s for s in secondary if s][:10],
        target_locations=[],
    )


def _keyword_text(item) -> str:  # type: ignore[no-untyped-def]
    """Keywords can be plain strings or dicts in the strategy
    schema. Extract a text label either way."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("keyword") or item.get("term") or item.get("text") or "")
    return str(item)


def _assets_from_packs(
    creative: CreativeAssetPack | None,
    job_pack: ImageGenerationJobPack | None,
) -> list[HandoffAssetReference]:
    out: list[HandoffAssetReference] = []
    if creative is not None:
        raw = creative.model_dump()
        for asset in raw.get("assets", [])[:6]:
            out.append(HandoffAssetReference(
                asset_id=asset.get("asset_id"),
                asset_kind=asset.get("asset_kind") or "creative_asset",
                label=asset.get("title") or asset.get("kind"),
            ))
    if job_pack is not None:
        for job in job_pack.jobs[:4]:
            out.append(HandoffAssetReference(
                asset_id=job.job_id,
                asset_kind="image_job",
                label=f"{job.piece_type} / variant {job.variant_id}",
                filename_hint=job.output_filename_suggestion,
            ))
    return out


def _default_landing_sections(
    *,
    strategy: CampaignStrategyReport,
    creative: CreativeAssetPack | None,
    job_pack: ImageGenerationJobPack | None,
) -> list[LandingSection]:
    headline = (
        strategy.executive_summary.headline if strategy.executive_summary
        else f"{strategy.client_slug} — campaign landing"
    )
    sections: list[LandingSection] = [
        LandingSection(
            name="hero",
            objective="Attention + value proposition in one screen.",
            body_copy=headline[:4000] or "Headline TBD",
            assets=_assets_from_packs(creative, job_pack)[:2],
            cta_label=_primary_cta(creative) or "Solicitar demo",
        ),
        LandingSection(
            name="value_proposition",
            objective="Three pillars that back the hero promise.",
            body_copy=_value_prop_text(strategy),
        ),
        LandingSection(
            name="proof",
            objective="Show traction (case studies, testimonials).",
            body_copy=_proof_text(strategy),
            assets=_assets_from_packs(creative, job_pack)[2:4],
        ),
        LandingSection(
            name="cta",
            objective="Close with the primary conversion.",
            body_copy=_primary_cta(creative) or "Solicitar demo",
            cta_label=_primary_cta(creative) or "Solicitar demo",
        ),
    ]
    return sections


__all__ = [
    "AtlasHandoffFactory",
    "DEFAULT_ATLAS_BRIDGE_RULE_SET_ID",
    "build_and_persist_atlas_handoff",
]
