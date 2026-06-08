"""MKT-9C regression tests for legal-domain templated improvements.

LEXIA Alpha Pilot 2 (templated path) surfaced that the strategy
report still defaulted to ``"Falta de tiempo"`` / ``"Sobrecarga
informativa"`` pains and that none of the legal vocabulary the
client supplied appeared in the social / email / reels copy.

These tests pin:

- Audience pain_points now derive from the intake's product
  feature list + audience anti-pattern detection (Excel /
  WhatsApp / carpetas).
- The keyword plan surfaces product-feature slugs as seeds
  (``expedientes`` / ``vencimientos`` / ``honorarios`` etc.)
  AND every preferred word from the intake.
- Social posts, emails and reels speak about the same concrete
  pain — not "tareas repetitivas" / "lo mismo de siempre".
- Forbidden phrases declared in the intake never appear in the
  persisted strategy report.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
LEXIA_INTAKE = REPO_ROOT / "examples" / "intake" / "lexia.json"

# Pains we expect to see derived from the intake's
# product_or_service field. Each test below uses a subset.
_EXPECTED_DOMAIN_NOUNS: tuple[str, ...] = (
    "expedientes",
    "vencimientos",
    "honorarios",
    "tareas",
    "informes a clientes",
    "seguimiento judicial",
    "antecedentes",
)

# Anti-pattern tools recognised in the audience description.
_EXPECTED_ANTI_TOOLS: tuple[str, ...] = (
    "Excel", "WhatsApp", "carpetas", "manuales",
)

_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "revoluciona la justicia",
    "la IA hace todo",
    "garantizado",
    "reemplaza al abogado",
    "el mejor del mercado",
)


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _build_lexia(tmp_path: Path) -> dict:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(LEXIA_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    raw = (
        tmp_path / "mem" / "lexia" / "campaign_strategy_report"
        / "current.json"
    ).read_text(encoding="utf-8")
    return json.loads(raw)


# ---------- pain extraction ----------


def test_audience_pains_no_longer_default_to_falta_de_tiempo(
    tmp_path: Path,
) -> None:
    report = _build_lexia(tmp_path)
    pains = report["target_audience"]["pain_points"]
    assert pains, "Expected at least one pain point"
    assert "Falta de tiempo" not in pains, (
        "Audience still defaults to the legacy 'Falta de tiempo' pain; "
        "extractor should pull from product features for a real intake."
    )
    assert "Sobrecarga informativa" not in pains, (
        "Audience still defaults to 'Sobrecarga informativa'."
    )


def test_audience_pains_mention_legal_domain_features(tmp_path: Path) -> None:
    report = _build_lexia(tmp_path)
    pains_blob = " | ".join(report["target_audience"]["pain_points"]).lower()
    # At least 2 domain nouns should appear across the pain set.
    hits = [n for n in _EXPECTED_DOMAIN_NOUNS if n in pains_blob]
    assert len(hits) >= 2, (
        f"Expected at least 2 legal-domain nouns in pains; got: "
        f"{report['target_audience']['pain_points']}"
    )


def test_audience_pains_can_include_anti_pattern_tool_mention(
    tmp_path: Path,
) -> None:
    report = _build_lexia(tmp_path)
    pains_blob = " | ".join(report["target_audience"]["pain_points"])
    # Either the anti-pattern tool synthesis OR one of the tools
    # appears in at least one pain phrase.
    assert any(tool in pains_blob for tool in _EXPECTED_ANTI_TOOLS), (
        f"Expected an anti-pattern tool mention in pains; got: "
        f"{report['target_audience']['pain_points']}"
    )


# ---------- desired outcomes ----------


def test_desired_outcomes_use_preferred_words_when_no_explicit_outcomes(
    tmp_path: Path,
) -> None:
    report = _build_lexia(tmp_path)
    outcomes = report["target_audience"]["desired_outcomes"]
    intake = json.loads(LEXIA_INTAKE.read_text(encoding="utf-8"))
    preferred = [w.lower() for w in intake["preferred_words"]]
    blob = " ".join(outcomes).lower()
    assert any(w in blob for w in preferred), (
        f"Outcomes did not weave in any preferred word: {outcomes}"
    )


# ---------- value proposition ----------


def test_value_proposition_headline_does_not_use_legacy_fallback(
    tmp_path: Path,
) -> None:
    report = _build_lexia(tmp_path)
    headline = report["value_proposition"]["headline"].lower()
    assert "falta de tiempo" not in headline, (
        f"Value-prop headline still uses 'falta de tiempo' fallback: "
        f"{headline!r}"
    )


def test_value_proposition_headline_mentions_domain_signal(
    tmp_path: Path,
) -> None:
    """The headline must surface either a domain feature noun
    (expedientes / vencimientos / ...) OR an anti-pattern tool
    mention (Excel / WhatsApp / carpetas / manuales). Either is
    LEXIA-specific enough to read as actionable."""
    report = _build_lexia(tmp_path)
    headline = report["value_proposition"]["headline"].lower()
    domain_signal_tokens = (
        *_EXPECTED_DOMAIN_NOUNS,
        *(t.lower() for t in _EXPECTED_ANTI_TOOLS),
    )
    assert any(tok in headline for tok in domain_signal_tokens), (
        f"Value-prop headline lacks a LEXIA-specific signal: {headline!r}"
    )


# ---------- keyword plan ----------


def test_keyword_plan_seeds_include_domain_features(tmp_path: Path) -> None:
    report = _build_lexia(tmp_path)
    cluster_labels = [c["label"].lower() for c in report["keyword_plan"]["clusters"]]
    blob = " | ".join(cluster_labels)
    domain_hits = [
        n.split()[0] for n in _EXPECTED_DOMAIN_NOUNS
        if n.split()[0] in blob
    ]
    assert len(domain_hits) >= 2, (
        f"Keyword plan does not surface enough legal-domain features. "
        f"Cluster labels: {cluster_labels}"
    )


def test_keyword_plan_hashtags_include_preferred_word(tmp_path: Path) -> None:
    report = _build_lexia(tmp_path)
    hashtags = " ".join(report["keyword_plan"]["hashtags"]).lower()
    intake = json.loads(LEXIA_INTAKE.read_text(encoding="utf-8"))
    preferred = [w.lower() for w in intake["preferred_words"]]
    assert any(w.replace(" ", "") in hashtags for w in preferred), (
        f"None of the preferred words made it to the hashtag set: "
        f"{report['keyword_plan']['hashtags']}"
    )


# ---------- social / email / reels echo the same pain ----------


def test_social_posts_speak_about_a_domain_pain(tmp_path: Path) -> None:
    report = _build_lexia(tmp_path)
    bodies = [
        " ".join([p.get("hook", ""), p.get("body", "")])
        for p in report["social_post_drafts"]
    ]
    blob = " ".join(bodies).lower()
    assert any(n in blob for n in _EXPECTED_DOMAIN_NOUNS), (
        f"Social posts mention no LEXIA domain feature. Sample: "
        f"{bodies[:1]!r}"
    )


def test_reels_voiceover_does_not_use_lo_mismo_de_siempre(
    tmp_path: Path,
) -> None:
    report = _build_lexia(tmp_path)
    scripts = report["reels_script_pack"]["scripts"]
    blob = " | ".join(
        " ".join(s.get("voiceover_lines", [])) for s in scripts
    ).lower()
    assert "lo mismo de siempre" not in blob, (
        "Reels voiceover still uses the boilerplate fallback "
        "'lo mismo de siempre' for the LEXIA intake."
    )


def test_reels_voiceover_mentions_a_domain_feature(tmp_path: Path) -> None:
    report = _build_lexia(tmp_path)
    scripts = report["reels_script_pack"]["scripts"]
    blob = " | ".join(
        " ".join(s.get("voiceover_lines", [])) for s in scripts
    ).lower()
    assert any(n in blob for n in _EXPECTED_DOMAIN_NOUNS), (
        "Reels voiceover never mentions a LEXIA domain noun."
    )


# ---------- forbidden phrases ----------


def test_no_forbidden_phrase_appears_in_user_facing_text(
    tmp_path: Path,
) -> None:
    """Forbidden phrases may legitimately appear in
    ``constraints`` / ``claims_to_avoid`` / the diagnosis claim
    guard — those are LISTS of what NOT to say. The test asserts
    they never appear in user-facing surfaces: headlines, hooks,
    bodies, CTAs, value-prop strings, voiceover lines."""
    report = _build_lexia(tmp_path)

    surfaces: list[str] = [
        report["executive_summary"]["headline"],
        report["executive_summary"]["one_liner"],
        report["value_proposition"]["headline"],
        *report["value_proposition"]["differentiators"],
        *report["value_proposition"]["proof_points"],
        report.get("channel_recommendation", {}).get("rationale_overall", ""),
        *(c["rationale"] for c in report["channel_recommendation"]["channels"]),
    ]
    for post in report["social_post_drafts"]:
        surfaces.extend([
            post.get("hook", ""),
            post.get("body", ""),
            post.get("cta", ""),
        ])
    for email in report["email_sequence"]["emails"]:
        surfaces.extend([
            email.get("subject", ""),
            email.get("body", ""),
            email.get("cta", ""),
        ])
    for script in report["reels_script_pack"]["scripts"]:
        surfaces.extend([script.get("hook", ""), script.get("cta", "")])
        surfaces.extend(script.get("voiceover_lines", []))
        surfaces.extend(script.get("on_screen_text", []))

    blob = " | ".join(surfaces).lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase.lower() not in blob, (
            f"Forbidden phrase {phrase!r} appears in user-facing copy."
        )


def test_diagnosis_surfaces_every_forbidden_phrase(tmp_path: Path) -> None:
    """Companion to the previous test: every forbidden phrase
    declared in the intake must surface in the diagnosis claim
    guard so the operator sees the list at review time."""
    report = _build_lexia(tmp_path)
    guard = " | ".join(report["diagnosis"]["challenges"]).lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase.lower() in guard, (
            f"Diagnosis claim guard does not list forbidden phrase "
            f"{phrase!r}."
        )


# ---------- low-level helpers ----------


def test_extract_product_features_finds_lexia_feature_list() -> None:
    from core.intake import ClientIntake, IntakeValidator
    from core.intake.normalizer import normalize_intake
    from core.strategy.templates import _extract_product_features

    raw = json.loads(LEXIA_INTAKE.read_text(encoding="utf-8"))
    intake = ClientIntake.model_validate(raw)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    feats = _extract_product_features(brief)
    # Stable subset of the expected list.
    feat_blob = " | ".join(feats).lower()
    for needle in ("expedientes", "vencimientos", "honorarios"):
        assert needle in feat_blob, (
            f"Feature extractor lost {needle!r}; got: {feats}"
        )


def test_extract_pains_returns_non_legacy_when_intake_is_rich() -> None:
    from core.intake import ClientIntake, IntakeValidator
    from core.intake.normalizer import normalize_intake
    from core.strategy.templates import _extract_pains_from_intake

    raw = json.loads(LEXIA_INTAKE.read_text(encoding="utf-8"))
    intake = ClientIntake.model_validate(raw)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    pains = _extract_pains_from_intake(brief)
    assert pains and pains != ["Falta de tiempo", "Sobrecarga informativa"], (
        f"Pain extractor still returns the legacy fallback for LEXIA: {pains}"
    )


def test_sanitize_forbidden_replaces_phrases() -> None:
    from core.strategy.templates import _sanitize_forbidden

    raw = "LEXIA revoluciona la justicia para abogados."
    out = _sanitize_forbidden(raw, ["revoluciona la justicia"])
    assert "revoluciona la justicia" not in out.lower()
    assert "[REDACTED]" in out
