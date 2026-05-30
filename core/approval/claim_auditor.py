"""Deterministic rules-based claim auditor over CampaignStrategyReport.

The auditor walks a known set of high-risk fields in the report and emits
:class:`ClaimDetection` records for every match. No LLM is involved.

Rules live in :data:`DEFAULT_RULES` as ``ClaimRule`` instances. Adding a
rule is a data change, not a code change.

Promotion to LLM-backed detection is a separate block that requires the
safety boundaries documented in ``docs/runtime/agent-backend-safety.md``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Final

from core.domain.enums import ClaimSeverity
from core.strategy.models import CampaignStrategyReport

from .models import (
    ClaimCategory,
    ClaimDetection,
    ClaimRule,
)

# Identifier of the default rule pack. Persisted alongside detections so
# the source of truth is auditable when packs are reviewed later.
DEFAULT_RULE_SET_ID = "default-rules.v1"


# ---------- Default rules ----------

# Each rule's ``pattern`` is a case-insensitive regex. Patterns favor
# precision over recall: false positives are expensive to triage.

DEFAULT_RULES: Final[tuple[ClaimRule, ...]] = (
    # --- Guaranteed outcomes (UNSAFE) ---
    ClaimRule(
        rule_id="guaranteed_outcome.guaranteed_word",
        category=ClaimCategory.GUARANTEED_OUTCOME,
        default_severity=ClaimSeverity.UNSAFE,
        description="Promesa de resultado garantizado.",
        pattern=r"\bgarantiz(?:ad[oa]s?|amos|o)\b",
        suggested_mitigation=(
            "Reemplazar por lenguaje condicional ('puede ayudarte a', "
            "'algunos clientes reportaron') o agregar disclaimer claro."
        ),
    ),
    ClaimRule(
        rule_id="guaranteed_outcome.te_aseguro",
        category=ClaimCategory.GUARANTEED_OUTCOME,
        default_severity=ClaimSeverity.UNSAFE,
        description="Compromiso personal de resultado.",
        pattern=r"\bte asegur(?:o|amos)\b",
        suggested_mitigation="Quitar el compromiso personal; usar evidencia verificable.",
    ),
    ClaimRule(
        rule_id="risk_free_claim.sin_riesgo",
        category=ClaimCategory.RISK_FREE_CLAIM,
        default_severity=ClaimSeverity.UNSAFE,
        description="Claim de ausencia total de riesgo.",
        pattern=r"\bsin riesgo\b",
        suggested_mitigation="Reemplazar por 'con garantía de devolución por X días' (si aplica).",
    ),
    ClaimRule(
        rule_id="risk_free_claim.money_back",
        category=ClaimCategory.RISK_FREE_CLAIM,
        default_severity=ClaimSeverity.RISKY,
        description="Garantía de devolución total — verificar política.",
        pattern=r"\b(?:devoluci[óo]n del 100%|garantizado o tu dinero|tu dinero de vuelta)\b",
        suggested_mitigation="Confirmar que la política de devolución existe y es ejecutable.",
    ),
    # --- Financial promises (UNSAFE) ---
    ClaimRule(
        rule_id="financial_promise.aumenta_ingresos",
        category=ClaimCategory.FINANCIAL_PROMISE,
        default_severity=ClaimSeverity.UNSAFE,
        description="Promesa cuantitativa de aumento de ingresos.",
        # ``aumentá / aumenta / aumente / aumentar / aumentamos`` — accents matter.
        pattern=r"\baument(?:a|á|e|ar|amos)\s+(?:tus|los|sus)?\s*ingresos\b",
        suggested_mitigation="Convertir en 'casos donde clientes reportaron X' con evidencia.",
    ),
    ClaimRule(
        rule_id="financial_promise.ahorra_dinero",
        category=ClaimCategory.FINANCIAL_PROMISE,
        default_severity=ClaimSeverity.RISKY,
        description="Promesa de ahorro económico no cuantificado.",
        pattern=r"\bahorr[áaae](?:r|mos|s|)?\s+(?:dinero|plata|tiempo y dinero)\b",
        suggested_mitigation="Cuantificar el ahorro con fuente o cambiar por 'puede ayudarte a optimizar costos'.",
    ),
    ClaimRule(
        rule_id="financial_promise.roi_garantizado",
        category=ClaimCategory.FINANCIAL_PROMISE,
        default_severity=ClaimSeverity.UNSAFE,
        description="ROI garantizado — promesa financiera.",
        pattern=r"\bROI\s+garantiz",
        suggested_mitigation="Eliminar — no se pueden garantizar retornos.",
    ),
    # --- Legal / tax (UNSAFE) ---
    ClaimRule(
        rule_id="legal_or_tax.deducible",
        category=ClaimCategory.LEGAL_OR_TAX,
        default_severity=ClaimSeverity.UNSAFE,
        description="Claim de deducibilidad impositiva.",
        pattern=r"\b(?:deducible|tax[\s-]?free|exento de impuestos)\b",
        suggested_mitigation="Quitar — claims fiscales requieren asesoría profesional y disclaimers.",
    ),
    # --- Medical / sensitive (UNSAFE) ---
    ClaimRule(
        rule_id="medical_or_sensitive.cura_trata_previene",
        category=ClaimCategory.MEDICAL_OR_SENSITIVE,
        default_severity=ClaimSeverity.UNSAFE,
        description="Claim médico — cura/trata/previene/diagnostica.",
        pattern=r"\b(?:cura|trata(?!miento de datos)|previene|diagn[oó]stic[ao])\b",
        suggested_mitigation=(
            "Usar lenguaje no clínico ('apoya', 'acompaña'). Claims médicos "
            "requieren respaldo regulatorio."
        ),
    ),
    # --- Superlatives (RISKY) ---
    ClaimRule(
        rule_id="superlative.somos_los_mejores",
        category=ClaimCategory.SUPERLATIVE,
        default_severity=ClaimSeverity.RISKY,
        description="Superlativo sin fundamento.",
        pattern=r"\bsomos los mejores\b|\bel\s+(?:#\s*)?1\s+(?:del\s+mercado|en)",
        suggested_mitigation="Reemplazar por evidencia específica ('usado por X clientes', ranking citado).",
    ),
    ClaimRule(
        rule_id="superlative.lider_absoluto",
        category=ClaimCategory.SUPERLATIVE,
        default_severity=ClaimSeverity.RISKY,
        description="Claim de liderazgo absoluto.",
        pattern=r"\bl[íi]der\s+(?:absoluto|del mercado|indiscutid[oa])\b",
        suggested_mitigation="Citar fuente o cambiar por 'uno de los líderes' / claim verificable.",
    ),
    # --- Competitor comparison (RISKY) ---
    ClaimRule(
        rule_id="competitor_comparison.mejor_que",
        category=ClaimCategory.COMPETITOR_COMPARISON,
        default_severity=ClaimSeverity.RISKY,
        description="Comparación directa contra un competidor con nombre.",
        # Match "mejor que <Capitalized>" (proper noun heuristic).
        pattern=r"\bmejor que\s+[A-Z][A-Za-z0-9_-]{1,40}\b",
        suggested_mitigation="Requiere evidencia comparativa publicable o cambio a 'diferente de'.",
    ),
    ClaimRule(
        rule_id="competitor_comparison.mas_rapido_que",
        category=ClaimCategory.COMPETITOR_COMPARISON,
        default_severity=ClaimSeverity.RISKY,
        description="Comparación de velocidad contra un competidor con nombre.",
        pattern=r"\bm[áa]s r[áa]pido que\s+[A-Z][A-Za-z0-9_-]{1,40}\b",
        suggested_mitigation="Adjuntar benchmark verificable o reformular.",
    ),
    # --- Exaggerated benefits (CAVEAT) ---
    ClaimRule(
        rule_id="exaggerated_benefit.increible_asombroso",
        category=ClaimCategory.EXAGGERATED_BENEFIT,
        default_severity=ClaimSeverity.CAVEAT,
        description="Adjetivos exagerados.",
        pattern=r"\b(?:increíble|incre[ií]ble|asombros[ao]|alucinante|revolucionari[ao]|brutal)\b",
        suggested_mitigation="Sustituir por descripción concreta del beneficio.",
    ),
    ClaimRule(
        rule_id="exaggerated_benefit.vas_a_flipar",
        category=ClaimCategory.EXAGGERATED_BENEFIT,
        default_severity=ClaimSeverity.CAVEAT,
        description="Lenguaje hyperbólico coloquial.",
        pattern=r"\bvas a flipar\b|\bte va(?:s)? a volar la cabeza\b",
        suggested_mitigation="Reemplazar por copy específico que describa el cambio.",
    ),
    # --- Artificial urgency (CAVEAT) ---
    ClaimRule(
        rule_id="artificial_urgency.solo_hoy",
        category=ClaimCategory.ARTIFICIAL_URGENCY,
        default_severity=ClaimSeverity.CAVEAT,
        description="Urgencia artificial (solo hoy).",
        pattern=r"\bsolo hoy\b|\b[úu]ltima oportunidad\b",
        suggested_mitigation="Solo si hay deadline verificable. Si no, quitar.",
    ),
    ClaimRule(
        rule_id="artificial_urgency.ultimas_unidades",
        category=ClaimCategory.ARTIFICIAL_URGENCY,
        default_severity=ClaimSeverity.CAVEAT,
        description="Escasez artificial — últimas N unidades.",
        pattern=r"\b[úu]ltimas?\s+\d+\s+(?:unidades|lugares|cupos|plazas)\b",
        suggested_mitigation="Verificar inventario real; si no es real, quitar.",
    ),
    ClaimRule(
        rule_id="artificial_urgency.termina_en",
        category=ClaimCategory.ARTIFICIAL_URGENCY,
        default_severity=ClaimSeverity.CAVEAT,
        description="Countdown (termina en N horas).",
        pattern=r"\btermina en\s+\d+\s+(?:horas|d[ií]as|minutos)\b",
        suggested_mitigation="Validar que el countdown es real y se respeta.",
    ),
    # --- Unsourced statistics (RISKY) ---
    ClaimRule(
        rule_id="unsourced_statistic.percent_no_source",
        category=ClaimCategory.UNSOURCED_STATISTIC,
        default_severity=ClaimSeverity.RISKY,
        description="Porcentaje sin fuente.",
        # Numbers with % sign, ignoring obviously safe contexts handled by review.
        pattern=r"\b\d{1,3}\s*%\b",
        suggested_mitigation="Citar fuente o quitar el dato cuantitativo.",
    ),
    ClaimRule(
        rule_id="unsourced_statistic.multiplier_no_source",
        category=ClaimCategory.UNSOURCED_STATISTIC,
        default_severity=ClaimSeverity.RISKY,
        description="Multiplicador sin fuente (3x, 10x).",
        pattern=r"\b\d{1,2}\s*x\s+(?:m[áa]s|mejor|r[áa]pido|veces)\b",
        suggested_mitigation="Citar fuente comparativa o quitar el multiplicador.",
    ),
    # --- Absolute claims (CAVEAT) ---
    ClaimRule(
        rule_id="absolute_claim.siempre_nunca",
        category=ClaimCategory.ABSOLUTE_CLAIM,
        default_severity=ClaimSeverity.CAVEAT,
        description="Claim absoluto (siempre / nunca).",
        pattern=r"\b(?:siempre funciona|nunca falla|todo el mundo)\b",
        suggested_mitigation="Suavizar con 'en la mayoría de los casos' o evidencia.",
    ),
    # --- Generic promise (CAVEAT) ---
    ClaimRule(
        rule_id="generic_promise.aumenta_ventas",
        category=ClaimCategory.GENERIC_PROMISE,
        default_severity=ClaimSeverity.CAVEAT,
        description="Promesa genérica sin contexto.",
        pattern=r"\baument[áa](?:r|mos)?\s+(?:tus|las)?\s*ventas\b",
        suggested_mitigation="Especificar mecanismo y mostrar evidencia.",
    ),
)


# ---------- Field walker ----------

def _iter_high_risk_fields(report: CampaignStrategyReport) -> Iterator[tuple[str, str]]:
    """Yield ``(path, text)`` pairs from the report's high-risk fields.

    The path uses dotted + bracketed JSON-pointer style so a reviewer can
    locate the offending text in the Markdown report.
    """
    # Executive summary
    yield "executive_summary.headline", report.executive_summary.headline
    yield "executive_summary.one_liner", report.executive_summary.one_liner

    # Value proposition
    yield "value_proposition.headline", report.value_proposition.headline
    for i, d in enumerate(report.value_proposition.differentiators):
        yield f"value_proposition.differentiators[{i}]", d
    for i, p in enumerate(report.value_proposition.proof_points):
        yield f"value_proposition.proof_points[{i}]", p

    # Email sequence
    for i, e in enumerate(report.email_sequence.emails):
        yield f"email_sequence.emails[{i}].subject", e.subject
        yield f"email_sequence.emails[{i}].preview_text", e.preview_text
        yield f"email_sequence.emails[{i}].body", e.body
        yield f"email_sequence.emails[{i}].cta", e.cta

    # Social posts
    for i, p in enumerate(report.social_post_drafts):
        yield f"social_post_drafts[{i}].hook", p.hook
        yield f"social_post_drafts[{i}].body", p.body
        yield f"social_post_drafts[{i}].cta", p.cta

    # Reels
    for i, s in enumerate(report.reels_script_pack.scripts):
        yield f"reels_script_pack.scripts[{i}].hook", s.hook
        for j, v in enumerate(s.voiceover_lines):
            yield f"reels_script_pack.scripts[{i}].voiceover_lines[{j}]", v
        for j, t in enumerate(s.on_screen_text):
            yield f"reels_script_pack.scripts[{i}].on_screen_text[{j}]", t
        yield f"reels_script_pack.scripts[{i}].cta", s.cta

    # Creative briefs
    for i, b in enumerate(report.creative_brief_pack.briefs):
        for j, c in enumerate(b.copy_overlay):
            yield f"creative_brief_pack.briefs[{i}].copy_overlay[{j}]", c
        if b.cta:
            yield f"creative_brief_pack.briefs[{i}].cta", b.cta

    # Suggested pieces (purpose is the only text-heavy field here)
    for i, sp in enumerate(report.suggested_pieces):
        yield f"suggested_pieces[{i}].purpose", sp.purpose


# ---------- Auditor ----------

class ClaimAuditor:
    """Walks a :class:`CampaignStrategyReport` against a rule set.

    Usage::

        auditor = ClaimAuditor()        # uses DEFAULT_RULES
        detections = auditor.audit(report)
    """

    def __init__(
        self,
        rules: Iterable[ClaimRule] | None = None,
        *,
        rule_set_id: str = DEFAULT_RULE_SET_ID,
    ) -> None:
        self._rules: tuple[ClaimRule, ...] = (
            tuple(rules) if rules is not None else DEFAULT_RULES
        )
        self._rule_set_id = rule_set_id
        # Compile patterns once. Invalid patterns surface here.
        self._compiled: list[tuple[ClaimRule, re.Pattern[str]]] = [
            (r, re.compile(r.pattern, re.IGNORECASE)) for r in self._rules
        ]

    # -------- public API --------

    @property
    def rule_set_id(self) -> str:
        return self._rule_set_id

    @property
    def rules(self) -> tuple[ClaimRule, ...]:
        return self._rules

    def audit(self, report: CampaignStrategyReport) -> list[ClaimDetection]:
        """Return every detection across the high-risk fields of ``report``."""
        out: list[ClaimDetection] = []
        for path, text in _iter_high_risk_fields(report):
            if not text:
                continue
            for rule, pattern in self._compiled:
                for m in pattern.finditer(text):
                    out.append(
                        ClaimDetection(
                            rule_id=rule.rule_id,
                            rule_description=rule.description,
                            category=rule.category,
                            severity=rule.default_severity,
                            text_span=m.group(0),
                            located_in=path,
                            requires_human_review=rule.requires_human_review,
                            suggested_mitigation=rule.suggested_mitigation,
                        )
                    )
        return out

    def audit_text(self, text: str, *, located_in: str = "<text>") -> list[ClaimDetection]:
        """Audit an arbitrary text span. Useful for tests and ad-hoc checks."""
        out: list[ClaimDetection] = []
        for rule, pattern in self._compiled:
            for m in pattern.finditer(text):
                out.append(
                    ClaimDetection(
                        rule_id=rule.rule_id,
                        rule_description=rule.description,
                        category=rule.category,
                        severity=rule.default_severity,
                        text_span=m.group(0),
                        located_in=located_in,
                        requires_human_review=rule.requires_human_review,
                        suggested_mitigation=rule.suggested_mitigation,
                    )
                )
        return out
