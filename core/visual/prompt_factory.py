"""VisualPromptFactory — assembles the Visual Direction Pack.

Given a strategy report (and optionally an approval pack + creative pack),
produces a :class:`VisualDirectionPack` with:

- A campaign-wide style guide.
- One :class:`PieceVisualDirection` per :class:`PieceType` (11 total).
- Two prompt variants per direction (A: editorial, B: bold contrast).
- A small set of global visual risks the designer should avoid.
- A pack-wide checklist.

Deterministic. No LLM. No image generation. No API. Same inputs → same pack.
"""

from __future__ import annotations

from typing import Any

from core.approval.models import ApprovalPack, ApprovalState
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative.models import (
    CreativeAssetPack,
    CreativeAssetState,
    ImagePromptAsset,
)
from core.domain.base import utcnow
from core.domain.enums import ChannelType, ClaimSeverity
from core.memory import Memory
from core.strategy.models import CampaignStrategyReport

from .models import (
    PieceVisualDirection,
    VisualChecklistItem,
    VisualDirectionPack,
    VisualPromptVariant,
    VisualRisk,
    VisualStyleGuide,
)
from .specs import (
    DEFAULT_PIECE_SPECS,
    PieceType,
    all_piece_types,
)

VISUAL_PACK_KIND = "visual_direction_pack"
SINGLETON_ID = "current"

# Identifier of the default rule set persisted on each pack.
DEFAULT_RULE_SET_ID = "default-visual-rules.v1"


# ---------- Helpers ----------

def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def _derive_state_for_directions(pack: ApprovalPack | None) -> CreativeAssetState:
    """Same derivation policy as MKT-3C, applied to directions."""
    if pack is None:
        return CreativeAssetState.NEEDS_REVIEW
    if pack.blocks_publish:
        return CreativeAssetState.BLOCKED
    if pack.state is ApprovalState.APPROVED:
        return CreativeAssetState.READY_FOR_PUBLISH
    if pack.overall_severity in (ClaimSeverity.RISKY, ClaimSeverity.UNSAFE):
        return CreativeAssetState.NEEDS_REVIEW
    return CreativeAssetState.DRAFT


def _checklist_for_direction(state: CreativeAssetState, piece_label: str) -> list[VisualChecklistItem]:
    items: list[VisualChecklistItem] = [
        VisualChecklistItem(
            title=f"Validar composición y safe zones del {piece_label}.",
            severity="must",
            category="composition",
        ),
        VisualChecklistItem(
            title="Verificar tipografía y contraste mínimo (AA).",
            severity="must",
            category="typography",
        ),
        VisualChecklistItem(
            title="Confirmar paleta dentro del rango brand.",
            severity="must",
            category="brand",
        ),
        VisualChecklistItem(
            title="Revisar accesibilidad: contraste de texto, alt text si aplica.",
            severity="should",
            category="accessibility",
        ),
        VisualChecklistItem(
            title="Verificar dimensiones y aspect ratio exactos.",
            severity="must",
            category="format",
        ),
    ]
    if state is CreativeAssetState.BLOCKED:
        items.append(
            VisualChecklistItem(
                title="BLOQUEADO: revisar Approval Pack y resolver claims antes de avanzar.",
                severity="blocker",
                category="claims",
            )
        )
    elif state is CreativeAssetState.NEEDS_REVIEW:
        items.append(
            VisualChecklistItem(
                title="Decisión humana pendiente antes de producir la pieza.",
                severity="must",
                category="operational",
            )
        )
    return items


def _global_checklist(state: CreativeAssetState) -> list[VisualChecklistItem]:
    items = [
        VisualChecklistItem(
            title="Revisar Style Guide con el cliente antes de producir.",
            severity="must",
            category="brand",
        ),
        VisualChecklistItem(
            title="Validar que ningún prompt referencia logos o IP de terceros.",
            severity="must",
            category="claims",
        ),
        VisualChecklistItem(
            title="Confirmar que los formatos cubren los canales activos.",
            severity="must",
            category="format",
        ),
        VisualChecklistItem(
            title="Hacer una pasada de accesibilidad sobre las piezas finales.",
            severity="should",
            category="accessibility",
        ),
    ]
    if state in (CreativeAssetState.BLOCKED, CreativeAssetState.NEEDS_REVIEW):
        items.append(
            VisualChecklistItem(
                title="Pack no aprobado todavía — pieces no pueden producirse para publicación.",
                severity="blocker" if state is CreativeAssetState.BLOCKED else "must",
                category="operational",
            )
        )
    return items


def _global_visual_risks(report: CampaignStrategyReport) -> list[VisualRisk]:
    """A small, deterministic risk set common to most campaigns."""
    risks = [
        VisualRisk(
            category="stock_cliche",
            severity="medium",
            description=(
                "Fotos stock genéricas (handshakes corporativos, equipo joven mirando una pantalla) "
                "saturan la categoría y reducen recordación."
            ),
            mitigation="Usar fotografía propia o ilustración editorial diferenciada.",
        ),
        VisualRisk(
            category="off_brand_palette",
            severity="medium",
            description=(
                "Gradientes púrpura/teal corporativos son default de muchas herramientas. "
                "Refuerzan la sensación 'tech genérico'."
            ),
            mitigation="Apostar a un acento sharp dentro de la paleta brand.",
        ),
        VisualRisk(
            category="accessibility",
            severity="medium",
            description=(
                "Contraste insuficiente entre overlay de texto y fondo es la causa #1 de bajo "
                "engagement en mobile."
            ),
            mitigation="Validar contraste AA con herramienta antes de subir.",
        ),
        VisualRisk(
            category="ai_artifacts",
            severity="medium",
            description=(
                "Manos deformes, texto ilegible y caras simétricas son tells de imágenes generadas "
                "sin curaduría. Bajan la credibilidad."
            ),
            mitigation="Si se usa imagen generada, curar manualmente y agregar grain/foto real overlay.",
        ),
        VisualRisk(
            category="ip_violation",
            severity="high",
            description=(
                "Prompts que mencionan marcas/logos de competidores reales generan riesgo legal."
            ),
            mitigation="Eliminar nombres de marcas reales del prompt; describir conceptos en abstracto.",
        ),
    ]
    if not report.competitor_benchmark.competitors:
        # No competitors known → less likely to accidentally name one.
        risks = [r for r in risks if r.category != "ip_violation"]
    return risks


def _style_guide_for_report(report: CampaignStrategyReport) -> VisualStyleGuide:
    audience_label = report.target_audience.label
    industry = report.diagnosis.industry or "marketing"
    return VisualStyleGuide(
        palette_primary=["#0F172A", "#22D3EE", "#F8FAFC"],
        palette_accent=["#F472B6"],
        typography_headline="Sans-serif dominante (Inter, Söhne o equivalente).",
        typography_body="Sans-serif legible (16–18px body en web).",
        typography_principles=[
            "Jerarquía clara: headline > subhead > body > CTA.",
            "Máximo 2 familias tipográficas por pieza.",
            "Tracking ajustado en titulares grandes.",
        ],
        overall_mood=(
            f"Editorial moderno y confiado, hecho para {audience_label.lower()}. "
            f"Tono profesional pero accesible para el rubro {industry}."
        ),
        visual_motifs=[
            "Espacio negativo dominante.",
            "Tipografía como elemento gráfico primario.",
            "Imágenes editoriales antes que ilustración decorativa.",
        ],
        composition_principles=[
            "Regla de tercios para sujetos.",
            "Anclaje de copy en zonas seguras del canal.",
            "Aire alrededor del CTA — nunca apretado al borde.",
        ],
        do_use=[
            "Fotografía editorial con personas reales del público.",
            "Paleta sobria con un acento sharp.",
            "Tipografía decisiva.",
        ],
        do_not_use=[
            "Handshakes corporativos stock.",
            "Gradientes púrpura/teal genéricos.",
            "Clip-art e iconografía decorativa.",
            "Caras simétricas con manos deformes (IA sin curar).",
        ],
    )


# ---------- Per-piece prompt assembly ----------

def _build_full_prompt(
    *,
    objective: str,
    audience: str,
    style: str,
    tone: str,
    composition: str,
    elements: list[str],
    text_overlay: list[str],
    palette: list[str],
    aspect_ratio: str,
    restrictions: list[str],
    intended_use: str,
) -> str:
    """Assemble the 12 fields into a ready-to-paste prompt string."""
    parts: list[str] = []
    parts.append(f"Objective: {objective}.")
    parts.append(f"Audience: {audience}.")
    parts.append(f"Visual style: {style}.")
    parts.append(f"Emotional tone: {tone}.")
    parts.append(f"Composition: {composition}.")
    if elements:
        parts.append("Key visual elements: " + ", ".join(elements) + ".")
    if text_overlay:
        parts.append("In-image text suggestion: " + " | ".join(text_overlay) + ".")
    if palette:
        parts.append("Suggested colors: " + ", ".join(palette) + ".")
    parts.append(f"Aspect ratio: {aspect_ratio}.")
    if restrictions:
        parts.append("Restrictions: " + "; ".join(restrictions) + ".")
    parts.append(f"Intended use: {intended_use}.")
    return " ".join(parts)


def _variant_a_editorial(
    *,
    piece_type: PieceType,
    audience: str,
    industry: str,
    product_name: str,
    differentiator: str,
    headline: str,
    style_palette: list[str],
    aspect_ratio: str,
    negative: str,
    intended_use: str,
) -> VisualPromptVariant:
    text_overlay = [_truncate(headline, 60), "Empezá hoy"]
    elements = [
        "Sujeto único en foco",
        "Espacio negativo amplio top-right para overlay",
        "Iluminación natural suave",
        "Detalles de producto en plano secundario",
    ]
    composition = (
        "Regla de tercios; sujeto en intersección izquierda; espacio negativo en cuadrante "
        "superior derecho reservado para headline overlay."
    )
    objective = _truncate(
        f"Reforzar la diferenciación de {product_name} para {audience} sin recurrir a stock cliché.",
        500,
    )
    full = _build_full_prompt(
        objective=objective,
        audience=audience,
        style="Editorial moderno, fotografía limpia, tipografía sans-serif dominante.",
        tone="Confiado, calmo, profesional.",
        composition=composition,
        elements=elements,
        text_overlay=text_overlay,
        palette=style_palette,
        aspect_ratio=aspect_ratio,
        restrictions=[
            "No stock cliché",
            "No gradientes púrpura/teal",
            "No copy excesivo sobre la imagen",
        ],
        intended_use=intended_use,
    )
    return VisualPromptVariant(
        variant_id="A",
        objective=objective,
        target_audience=audience,
        visual_style="Editorial moderno, fotografía limpia, sans-serif dominante.",
        emotional_tone="Confiado, calmo, profesional.",
        composition=composition,
        in_image_text=text_overlay,
        visual_elements=elements,
        suggested_colors=style_palette,
        aspect_ratio=aspect_ratio,
        restrictions=[
            "No stock cliché",
            "No gradientes púrpura/teal",
            "No copy excesivo sobre la imagen",
        ],
        negative_prompt=negative,
        intended_use=intended_use,
        full_prompt_text=full,
    )


def _variant_b_bold(
    *,
    piece_type: PieceType,
    audience: str,
    industry: str,
    product_name: str,
    differentiator: str,
    headline: str,
    style_palette: list[str],
    aspect_ratio: str,
    negative: str,
    intended_use: str,
) -> VisualPromptVariant:
    text_overlay = [_truncate(differentiator or headline, 60), "Probalo"]
    elements = [
        "Tipografía oversize como gráfico principal",
        "Color flat de alto contraste",
        "Iconografía geométrica minimal",
        "Producto en silueta o detail crop",
    ]
    composition = (
        "Tipografía como elemento dominante; fondo de color sólido; jerarquía visual headline > "
        "subhead > CTA."
    )
    objective = _truncate(
        f"Capturar atención en feed con tipografía bold y contraste alto que distinga "
        f"{product_name} del default de la categoría.",
        500,
    )
    full = _build_full_prompt(
        objective=objective,
        audience=audience,
        style="Bold typographic poster, color flat alto contraste, sin foto fotográfica.",
        tone="Directo, asertivo, irreverente sin caer en humor barato.",
        composition=composition,
        elements=elements,
        text_overlay=text_overlay,
        palette=style_palette,
        aspect_ratio=aspect_ratio,
        restrictions=[
            "No fotografía realista",
            "No degradados decorativos",
            "Mantener máximo 2 tipografías",
        ],
        intended_use=intended_use,
    )
    return VisualPromptVariant(
        variant_id="B",
        objective=objective,
        target_audience=audience,
        visual_style="Bold typographic poster, color flat, alto contraste.",
        emotional_tone="Directo, asertivo, irreverente.",
        composition=composition,
        in_image_text=text_overlay,
        visual_elements=elements,
        suggested_colors=style_palette,
        aspect_ratio=aspect_ratio,
        restrictions=[
            "No fotografía realista",
            "No degradados decorativos",
            "Mantener máximo 2 tipografías",
        ],
        negative_prompt=negative,
        intended_use=intended_use,
        full_prompt_text=full,
    )


# ---------- Factory ----------

class VisualPromptFactory:
    """Build / persist / load a :class:`VisualDirectionPack`."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # ---------- build ----------

    def build(
        self,
        report: CampaignStrategyReport,
        approval_pack: ApprovalPack | None = None,
        creative_pack: CreativeAssetPack | None = None,
    ) -> VisualDirectionPack:
        default_state = _derive_state_for_directions(approval_pack)
        blocks_publish = (
            approval_pack.blocks_publish if approval_pack is not None else False
        )

        style_guide = _style_guide_for_report(report)
        product_name = (
            report.executive_summary.headline.split(":")[0].split(".")[0].strip()
            or "tu producto"
        )
        audience = report.target_audience.label
        differentiator = (
            report.value_proposition.differentiators[0]
            if report.value_proposition.differentiators
            else report.value_proposition.headline
        )
        headline = report.value_proposition.headline
        industry = report.diagnosis.industry or "rubro"

        # Index source creative image prompts by intended_use (when present)
        # so we can attach a reference when a match is found.
        source_image_prompt_by_use: dict[str, ImagePromptAsset] = {}
        if creative_pack is not None:
            for ip in creative_pack.image_prompts:
                source_image_prompt_by_use.setdefault(ip.intended_use, ip)

        # Index source assets by piece_type for scheduling backfill.
        source_asset_dates: dict[PieceType, tuple[str | None, Any]] = {}
        if creative_pack is not None:
            # Map flyer formats / channels to PieceType matches.
            for cp_asset in creative_pack.flyers:
                if cp_asset.format.value == "1:1":
                    source_asset_dates[PieceType.FLYER_SQUARE] = (
                        cp_asset.asset_id,
                        cp_asset.scheduled_for,
                    )
                elif cp_asset.format.value == "4:5":
                    source_asset_dates[PieceType.FLYER_VERTICAL] = (
                        cp_asset.asset_id,
                        cp_asset.scheduled_for,
                    )
            for cp_asset in creative_pack.social_posts:
                # First social post per channel becomes the scheduled match.
                if cp_asset.channel == ChannelType.INSTAGRAM:
                    source_asset_dates.setdefault(
                        PieceType.INSTAGRAM_POST,
                        (cp_asset.asset_id, cp_asset.scheduled_for),
                    )
                elif cp_asset.channel == ChannelType.LINKEDIN:
                    source_asset_dates.setdefault(
                        PieceType.LINKEDIN_POST_GRAPHIC,
                        (cp_asset.asset_id, cp_asset.scheduled_for),
                    )
                elif cp_asset.channel == ChannelType.FACEBOOK:
                    source_asset_dates.setdefault(
                        PieceType.FACEBOOK_POST,
                        (cp_asset.asset_id, cp_asset.scheduled_for),
                    )
            for cp_asset in creative_pack.reels:
                source_asset_dates.setdefault(
                    PieceType.REELS_COVER,
                    (cp_asset.asset_id, cp_asset.scheduled_for),
                )
            for cp_asset in creative_pack.emails:
                source_asset_dates.setdefault(
                    PieceType.EMAIL_HEADER,
                    (cp_asset.asset_id, cp_asset.scheduled_for),
                )

        # Build one direction per piece type (always 11).
        directions: list[PieceVisualDirection] = []
        for pt in all_piece_types():
            spec = DEFAULT_PIECE_SPECS[pt]
            intended_use_label = pt.value

            # Match source creative image prompt by intended_use heuristic.
            src_img_prompt = None
            if pt in (PieceType.INSTAGRAM_CAROUSEL,):
                src_img_prompt = source_image_prompt_by_use.get("instagram_carousel")
            elif pt is PieceType.LANDING_HERO:
                src_img_prompt = source_image_prompt_by_use.get("hero_image")
            elif pt is PieceType.REELS_COVER:
                src_img_prompt = source_image_prompt_by_use.get("reels_thumbnail")

            source_asset_id, source_date = source_asset_dates.get(pt, (None, None))

            variant_a = _variant_a_editorial(
                piece_type=pt,
                audience=audience,
                industry=industry,
                product_name=product_name,
                differentiator=differentiator,
                headline=headline,
                style_palette=style_guide.palette_primary,
                aspect_ratio=spec.aspect_ratio,
                negative=spec.typical_negative_prompt,
                intended_use=intended_use_label,
            )
            variant_b = _variant_b_bold(
                piece_type=pt,
                audience=audience,
                industry=industry,
                product_name=product_name,
                differentiator=differentiator,
                headline=headline,
                style_palette=style_guide.palette_primary + style_guide.palette_accent,
                aspect_ratio=spec.aspect_ratio,
                negative=spec.typical_negative_prompt,
                intended_use=intended_use_label,
            )

            d = PieceVisualDirection(
                piece_type=pt,
                channel=spec.channel,
                spec=spec,
                prompt_variants=[variant_a, variant_b],
                state=default_state,
                checklist=_checklist_for_direction(default_state, pt.value),
                source_creative_image_prompt_id=(
                    src_img_prompt.asset_id if src_img_prompt is not None else None
                ),
                source_creative_asset_id=source_asset_id,
                scheduled_for=source_date,
            )
            directions.append(d)

        now = utcnow()
        pack = VisualDirectionPack(
            client_slug=report.client_slug,
            report_id=report.report_id,
            report_contract_version=report.contract_version,
            approval_pack_id=approval_pack.pack_id if approval_pack else None,
            approval_pack_contract_version=(
                approval_pack.contract_version if approval_pack else None
            ),
            creative_pack_id=creative_pack.pack_id if creative_pack else None,
            creative_pack_contract_version=(
                creative_pack.contract_version if creative_pack else None
            ),
            derived_overall_state=default_state,
            blocks_publish=blocks_publish,
            style_guide=style_guide,
            directions=directions,
            global_visual_risks=_global_visual_risks(report),
            global_checklist=_global_checklist(default_state),
            created_at=now,
            updated_at=now,
            rule_set_id=DEFAULT_RULE_SET_ID,
        )
        return pack

    # ---------- persistence ----------

    def persist(self, pack: VisualDirectionPack) -> None:
        existed = self._memory.exists(
            pack.client_slug, VISUAL_PACK_KIND, SINGLETON_ID
        )
        self._memory.put(
            pack.client_slug,
            VISUAL_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        self._emit_event(
            client_slug=pack.client_slug,
            payload={
                "pack_id": pack.pack_id,
                "report_id": pack.report_id,
                "approval_pack_id": pack.approval_pack_id,
                "creative_pack_id": pack.creative_pack_id,
                "derived_overall_state": pack.derived_overall_state.value,
                "blocks_publish": pack.blocks_publish,
                "total_directions": pack.total_directions,
                "total_prompt_variants": pack.total_prompt_variants,
                "action": "updated" if existed else "created",
            },
        )

    def load(self, client_slug: str) -> VisualDirectionPack:
        raw = self._memory.get(client_slug, VISUAL_PACK_KIND, SINGLETON_ID)
        return VisualDirectionPack.model_validate(raw)

    # ---------- internals ----------

    def _emit_event(
        self, *, client_slug: str, payload: dict[str, Any]
    ) -> None:
        self._memory.append_audit_event_atomic(
            client_slug,
            lambda prev_hash_arg: AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor="visual_prompt_factory",
                occurred_at=utcnow(),
                client_slug=client_slug,
                payload={"visual_pack": payload},
                prev_hash=prev_hash_arg,
            ),
        )


def build_and_persist(
    memory: Memory,
    report: CampaignStrategyReport,
    approval_pack: ApprovalPack | None = None,
    creative_pack: CreativeAssetPack | None = None,
) -> VisualDirectionPack:
    factory = VisualPromptFactory(memory)
    pack = factory.build(report, approval_pack, creative_pack)
    factory.persist(pack)
    return pack


__all__ = [
    "VISUAL_PACK_KIND",
    "SINGLETON_ID",
    "DEFAULT_RULE_SET_ID",
    "VisualPromptFactory",
    "build_and_persist",
]
