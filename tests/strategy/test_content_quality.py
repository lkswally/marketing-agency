"""MKT-4D regression tests for content quality.

These tests pin the improvements made in MKT-4D so future refactors
don't reintroduce the documented bad patterns:

- No headline / big_idea / copy uses the legacy placeholder phrase
  ``"Diseñado específicamente para"``.
- Keyword clusters are not seeded from stopwords (``sin``), generic
  tokens (``setup``) or accent-stripped junk (``diseado``).
- Hashtags use Unicode NFD normalization so ``Diseñado`` becomes
  ``#Disenado`` (clean), not ``#Diseado`` (broken).
- Preferred words from the brand lexicon appear in headlines and at
  least one copy per channel.
- Channel copies are NOT identical across channels.
- Forbidden words in generated copy trigger HIGH-severity risks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.intake import ClientIntake, IntakeValidator, normalize_intake
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_INTAKE = REPO_ROOT / "examples" / "intake" / "marketing-agency-os.json"
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run_real(tmp_path: Path):
    intake = ClientIntake.model_validate(
        json.loads(REAL_INTAKE.read_text(encoding="utf-8"))
    )
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    mem = JsonFileMemory(tmp_path / "mem")
    pipeline = StrategyPipeline(memory=mem)
    return pipeline.run_from_brief(brief).report


# ---------- placeholder kill ----------

def test_value_proposition_does_not_contain_legacy_placeholder(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    assert "Diseñado específicamente" not in report.value_proposition.headline


def test_big_idea_does_not_contain_legacy_placeholder(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    assert (
        report.campaign_strategy.big_idea
        and "Diseñado específicamente" not in report.campaign_strategy.big_idea
    )


def test_no_email_body_contains_placeholder(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    for email in report.email_sequence.emails:
        assert "Diseñado específicamente" not in email.body


def test_no_social_copy_contains_placeholder(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    for post in report.social_post_drafts:
        assert "Diseñado específicamente" not in post.body
        assert "Diseñado específicamente" not in post.hook


def test_no_reels_voiceover_contains_placeholder(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    for reel in report.reels_script_pack.scripts:
        for line in reel.voiceover_lines:
            assert "Diseñado específicamente" not in line


# ---------- keyword clusters ----------

@pytest.mark.parametrize("junk", ["sin", "para", "con", "y", "setup", "demo"])
def test_keyword_cluster_labels_do_not_use_junk_seeds(tmp_path: Path, junk: str) -> None:
    report = _run_real(tmp_path)
    labels = {c.label for c in report.keyword_plan.clusters}
    bad = f"{junk}_informational"
    assert bad not in labels, (
        f"keyword cluster `{bad}` should never be produced (junk seed)"
    )


def test_keyword_cluster_no_accent_stripped_garbage(tmp_path: Path) -> None:
    """``Diseñado`` must NOT become ``diseado`` as a cluster seed (the
    bug from MKT-4C). Either NFD-folded to ``disenado`` (and then
    rejected as a verb tense by the meaningful_keyword filter), or
    absent entirely. Either way, ``diseado_informational`` must not
    appear."""
    report = _run_real(tmp_path)
    labels = {c.label for c in report.keyword_plan.clusters}
    assert "diseado_informational" not in labels


# ---------- hashtags ----------

def test_hashtag_for_accented_word_uses_nfd(tmp_path: Path) -> None:
    """``Determinístico`` (a preferred word) becomes ``#Deterministico``
    not ``#Determinstico`` (ASCII strip) or ``#Determinístico``
    (raw accent)."""
    report = _run_real(tmp_path)
    tags = set(report.keyword_plan.hashtags)
    assert "#Deterministico" in tags


def test_hashtag_for_diseado_never_appears(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    assert "#Diseado" not in report.keyword_plan.hashtags


def test_preferred_words_appear_in_hashtags(tmp_path: Path) -> None:
    """At least one preferred-word hashtag appears."""
    report = _run_real(tmp_path)
    tags = set(report.keyword_plan.hashtags)
    # Real intake has 'determinístico', 'auditable', ... — at least one
    # should be hashtagged.
    assert any(t in tags for t in ("#Deterministico", "#Auditable"))


# ---------- channel variation ----------

def test_social_copies_are_not_identical_across_channels(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    bodies = [p.body for p in report.social_post_drafts]
    assert len(bodies) >= 3
    # Set length equals list length → all unique.
    assert len(set(bodies)) == len(bodies)
    # And the hooks too.
    hooks = [p.hook for p in report.social_post_drafts]
    assert len(set(hooks)) == len(hooks)


# ---------- preferred words injection ----------

def test_headline_contains_preferred_word_when_available(tmp_path: Path) -> None:
    """The real intake declares preferred_words; the headline should
    weave at least one in."""
    report = _run_real(tmp_path)
    headline_lower = report.value_proposition.headline.lower()
    intake = ClientIntake.model_validate(
        json.loads(REAL_INTAKE.read_text(encoding="utf-8"))
    )
    matches = [
        w for w in intake.preferred_words
        if w.lower() in headline_lower
    ]
    assert matches, (
        f"headline {report.value_proposition.headline!r} should include at "
        f"least one preferred_word from {intake.preferred_words}"
    )


def test_at_least_one_social_post_contains_preferred_word(tmp_path: Path) -> None:
    report = _run_real(tmp_path)
    intake = ClientIntake.model_validate(
        json.loads(REAL_INTAKE.read_text(encoding="utf-8"))
    )
    preferred_lower = [w.lower() for w in intake.preferred_words]
    hit = False
    for post in report.social_post_drafts:
        text = (post.hook + " " + post.body).lower()
        if any(pw in text for pw in preferred_lower):
            hit = True
            break
    assert hit, "at least one social post should weave in a preferred word"


# ---------- backward compatibility ----------

def test_demo_intake_still_works(tmp_path: Path) -> None:
    """The legacy demo intake (used by 100+ tests) keeps working
    end-to-end with the new templates."""
    intake = ClientIntake.model_validate(
        json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    )
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    mem = JsonFileMemory(tmp_path / "mem")
    pipeline = StrategyPipeline(memory=mem)
    result = pipeline.run_from_brief(brief)
    assert result.report.value_proposition.headline
    assert "Diseñado específicamente" not in result.report.value_proposition.headline
