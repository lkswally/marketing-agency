"""MKT-9D regression tests for industry-aware tone templates.

A real-business alpha pilot (anonymized here as LEGALCASE DEMO) surfaced that even after MKT-9C the
templated backend used SaaS-flavoured connectors ("en concreto",
"3 decisiones claros que tomamos esta semana", "Probalo hoy")
for a legaltech intake. MKT-9D adds the ``legal-pro`` tone
family and routes legal / legaltech briefs to it.

These tests pin:

- ``tone_family_for_brief`` returns ``"legal-pro"`` for LEGALCASE DEMO.
- The same returns the brand-tone classification for a non-legal
  intake (no regression on demo-business).
- LEGALCASE DEMO social posts use the sober vocabulary
  (``en la práctica``, ``ordenado``, ``estudio``) and DROP the
  legacy SaaS phrases (``Probalo hoy``, ``qué probamos, qué
  descartamos``, ``decisiones claros``).
- LEGALCASE DEMO emails open with "Estimado/a" (formal) and ``En la
  práctica del estudio`` (legal-pro opener).
- LEGALCASE DEMO reels never say "Probalo hoy" / "Probalo gratis".
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGALCASE_DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "legalcase-demo.json"
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"

# Phrases that read SaaS-genérico in a legaltech context. None of
# these may appear in body copy for LEGALCASE DEMO.
_LEGAL_PRO_BANNED_PHRASES: tuple[str, ...] = (
    "decisiones claros",
    "decisiones claro",
    "qué probamos, qué descartamos",
    "probalo hoy",
    "probalo gratis",
    "lo que probamos esta semana",
    "El problema no era la herramienta",
    "Carrusel con la decisión",
)

# Tokens that signal the legal-pro family has taken effect.
_LEGAL_PRO_EXPECTED_TOKENS: tuple[str, ...] = (
    "en la práctica",
    "estudio",
    "ordena",
    "pedir demo",
    "reservar",
    "estimado/a",
    "para el estudio",
)


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _build_intake(tmp_path: Path, intake: Path) -> dict:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(intake),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    slug = json.loads(stdout)["client_slug"]
    raw = (
        tmp_path / "mem" / slug / "campaign_strategy_report"
        / "current.json"
    ).read_text(encoding="utf-8")
    return json.loads(raw)


# ---------- tone family classification ----------


def test_tone_family_for_legalcase_demo_is_legal_pro() -> None:
    from core.intake import ClientIntake, IntakeValidator
    from core.intake.normalizer import normalize_intake
    from core.strategy.style import tone_family_for_brief

    raw = json.loads(LEGALCASE_DEMO_INTAKE.read_text(encoding="utf-8"))
    intake = ClientIntake.model_validate(raw)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    assert tone_family_for_brief(brief) == "legal-pro"


def test_tone_family_for_demo_business_is_not_legal_pro() -> None:
    from core.intake import ClientIntake, IntakeValidator
    from core.intake.normalizer import normalize_intake
    from core.strategy.style import tone_family_for_brief

    raw = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    intake = ClientIntake.model_validate(raw)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    family = tone_family_for_brief(brief)
    assert family != "legal-pro", (
        f"Demo intake (non-legal) was misclassified as legal-pro: {family}"
    )


# ---------- LEGALCASE DEMO social posts use sober vocabulary ----------


def test_legalcase_demo_social_posts_drop_saas_phrases(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    bodies = " | ".join(
        f"{p.get('hook','')} {p.get('body','')} {p.get('cta','')}"
        for p in report["social_post_drafts"]
    ).lower()
    for banned in _LEGAL_PRO_BANNED_PHRASES:
        assert banned.lower() not in bodies, (
            f"LEGALCASE DEMO social posts still contain SaaS phrase {banned!r}"
        )


def test_legalcase_demo_social_posts_use_legal_pro_signals(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    bodies = " | ".join(
        f"{p.get('hook','')} {p.get('body','')} {p.get('cta','')}"
        for p in report["social_post_drafts"]
    ).lower()
    hits = [t for t in _LEGAL_PRO_EXPECTED_TOKENS if t in bodies]
    assert len(hits) >= 3, (
        f"LEGALCASE DEMO social posts contain only {len(hits)} legal-pro signal(s): "
        f"{hits}. Expected at least 3."
    )


def test_legalcase_demo_social_post_ctas_are_sober(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    ctas = {p.get("cta", "") for p in report["social_post_drafts"]}
    forbidden_ctas = {"Mirá →", "Probalo →", "Probalo hoy"}
    assert not (ctas & forbidden_ctas), (
        f"LEGALCASE DEMO social CTAs still include SaaS-flavoured options: "
        f"{ctas & forbidden_ctas}"
    )


# ---------- LEGALCASE DEMO emails ----------


def test_legalcase_demo_emails_use_formal_opener(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    bodies = " | ".join(e["body"] for e in report["email_sequence"]["emails"])
    # Legal-pro emails open with "Estimado/a" (formal Spanish).
    assert "Estimado/a" in bodies, (
        f"LEGALCASE DEMO emails do not open with 'Estimado/a': sample = "
        f"{report['email_sequence']['emails'][0]['body'][:120]!r}"
    )


def test_legalcase_demo_emails_use_legal_pro_opener_phrase(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    bodies = " | ".join(e["body"] for e in report["email_sequence"]["emails"])
    assert "En la práctica del estudio" in bodies, (
        "LEGALCASE DEMO email bodies do not contain the legal-pro opener "
        "'En la práctica del estudio:'"
    )


def test_legalcase_demo_emails_cta_avoids_saas_flavours(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    ctas = {e["cta"] for e in report["email_sequence"]["emails"]}
    saas_ctas = {"Activar con descuento"}
    assert not (ctas & saas_ctas), (
        f"LEGALCASE DEMO email CTAs still include SaaS-flavoured options: "
        f"{ctas & saas_ctas}"
    )


# ---------- LEGALCASE DEMO reels ----------


def test_legalcase_demo_reels_never_say_probalo_hoy(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    blob = " | ".join(
        " ".join(s.get("voiceover_lines", []))
        + " " + s.get("cta", "")
        for s in report["reels_script_pack"]["scripts"]
    ).lower()
    for banned in ("probalo hoy", "probalo gratis", "probalo."):
        assert banned not in blob, (
            f"LEGALCASE DEMO reels still contain SaaS phrase {banned!r}"
        )


def test_legalcase_demo_reels_use_pedir_demo_closer(tmp_path: Path) -> None:
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    blob = " | ".join(
        " ".join(s.get("voiceover_lines", []))
        + " " + s.get("cta", "")
        for s in report["reels_script_pack"]["scripts"]
    ).lower()
    assert "pedir demo" in blob or "pedí una demo" in blob, (
        "LEGALCASE DEMO reels do not close with the legal-pro 'Pedir demo' / "
        "'Pedí una demo' CTA."
    )


# ---------- forbidden_words guard still holds ----------


def test_legalcase_demo_forbidden_phrases_never_in_body_copy(tmp_path: Path) -> None:
    """Re-run the MKT-9C guard on the post-MKT-9D output."""
    report = _build_intake(tmp_path, LEGALCASE_DEMO_INTAKE)
    forbidden = (
        "revoluciona la justicia",
        "la IA hace todo",
        "garantizado",
        "reemplaza al abogado",
        "el mejor del mercado",
    )
    surfaces: list[str] = [
        report["executive_summary"]["headline"],
        report["executive_summary"]["one_liner"],
        report["value_proposition"]["headline"],
        *report["value_proposition"]["differentiators"],
        *report["value_proposition"]["proof_points"],
    ]
    for post in report["social_post_drafts"]:
        surfaces.extend([post.get("hook", ""), post.get("body", ""), post.get("cta", "")])
    for email in report["email_sequence"]["emails"]:
        surfaces.extend([email.get("subject", ""), email.get("body", ""), email.get("cta", "")])
    for script in report["reels_script_pack"]["scripts"]:
        surfaces.extend([script.get("hook", ""), script.get("cta", "")])
        surfaces.extend(script.get("voiceover_lines", []))
    blob = " | ".join(surfaces).lower()
    for phrase in forbidden:
        assert phrase.lower() not in blob, (
            f"Forbidden phrase {phrase!r} appears in user-facing copy."
        )


# ---------- non-legal intake does not regress ----------


def test_demo_business_still_uses_default_tone(tmp_path: Path) -> None:
    """Pin: changing to the brief-aware helpers must NOT route a
    non-legal intake through legal-pro templates. Demo-business
    intake should still emit the legacy SaaS-style phrases (or
    at least NOT the legal-pro ones)."""
    report = _build_intake(tmp_path, DEMO_INTAKE)
    bodies = " | ".join(
        f"{p.get('hook','')} {p.get('body','')}"
        for p in report["social_post_drafts"]
    ).lower()
    # The demo intake should not show the legal-pro opener.
    assert "en la práctica del estudio" not in bodies
    # And the demo emails should still open with "Hola," not
    # "Estimado/a".
    email_blob = " | ".join(
        e["body"] for e in report["email_sequence"]["emails"]
    )
    assert "Hola," in email_blob, (
        "Demo business emails regressed away from informal 'Hola,'"
    )
