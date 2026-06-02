"""Tests for the MKT-4D style helpers."""

from __future__ import annotations

import pytest

from core.strategy.style import (
    contains_forbidden,
    first_meaningful_token,
    fold_diacritics,
    is_meaningful_keyword,
    make_hashtag,
    matches_bad_example_pattern,
    normalize_for_slug,
    pick_preferred_word,
    tone_adjective,
    tone_connector,
    tone_opener,
)

# ---------- fold_diacritics ----------

@pytest.mark.parametrize(
    "src,expected",
    [
        ("Diseñado", "Disenado"),
        ("acción", "accion"),
        ("café", "cafe"),
        ("año", "ano"),
        ("über", "uber"),
        ("ASCII", "ASCII"),
        ("", ""),
    ],
)
def test_fold_diacritics(src: str, expected: str) -> None:
    assert fold_diacritics(src) == expected


# ---------- normalize_for_slug ----------

def test_normalize_for_slug_basic() -> None:
    assert normalize_for_slug("Diseñado específicamente!") == "disenado especificamente"


def test_normalize_for_slug_collapses_whitespace() -> None:
    assert normalize_for_slug("  multi   space  ") == "multi space"


def test_normalize_for_slug_drops_punctuation() -> None:
    assert normalize_for_slug("¡Hola! ¿Qué tal?") == "hola que tal"


def test_normalize_for_slug_handles_empty() -> None:
    assert normalize_for_slug("") == ""
    assert normalize_for_slug(None) == ""  # type: ignore[arg-type]


# ---------- make_hashtag ----------

def test_make_hashtag_folds_accents() -> None:
    assert make_hashtag("Diseñado") == "#Disenado"


def test_make_hashtag_pascal_case() -> None:
    assert make_hashtag("marketing automation") == "#MarketingAutomation"


def test_make_hashtag_rejects_too_short() -> None:
    assert make_hashtag("ab") is None
    assert make_hashtag("a") is None


def test_make_hashtag_rejects_too_long() -> None:
    assert make_hashtag("a" * 50) is None


def test_make_hashtag_rejects_stopword() -> None:
    assert make_hashtag("sin") is None
    assert make_hashtag("para") is None


def test_make_hashtag_handles_empty() -> None:
    assert make_hashtag("") is None
    assert make_hashtag("   ") is None
    assert make_hashtag("!!!") is None


# ---------- is_meaningful_keyword ----------

@pytest.mark.parametrize(
    "word,ok",
    [
        ("pipeline", True),
        ("auditable", True),
        ("sin", False),       # stopword
        ("para", False),       # stopword
        ("set", False),        # too short (3)
        ("setup", False),      # generic
        ("demo", False),       # generic
        ("", False),
        ("Diseñado", True),    # 8 chars, not stopword (verb tense, would still be kept)
    ],
)
def test_is_meaningful_keyword(word: str, ok: bool) -> None:
    assert is_meaningful_keyword(word) is ok


def test_first_meaningful_token_skips_stopwords() -> None:
    assert first_meaningful_token("sin contratos largos") == "contratos"


def test_first_meaningful_token_strips_punctuation() -> None:
    assert first_meaningful_token("Resuelve un dolor concreto: falta") == "resuelve"


def test_first_meaningful_token_returns_none_for_all_junk() -> None:
    assert first_meaningful_token("y o a") is None
    assert first_meaningful_token("") is None


# ---------- tone helpers ----------

def test_tone_adjective_matches_family() -> None:
    assert tone_adjective(["técnico-pragmático"]) == "preciso"
    assert tone_adjective(["anti-marketing-hueco"]) == "directo"
    assert tone_adjective(["honesto"]) == "honesto"


def test_tone_adjective_neutral_fallback() -> None:
    assert tone_adjective([]) == "práctico"
    assert tone_adjective(["completamente inventado"]) == "práctico"


def test_tone_connector_per_family() -> None:
    assert tone_connector(["irreverente"]) == "honestamente"
    assert tone_connector(["claro"]) == "en concreto"


def test_tone_opener_per_family() -> None:
    assert tone_opener(["técnico-pragmático"]) == "Sin vueltas:"
    assert tone_opener(["calido"]) == "Te lo decimos así:"


# ---------- pick_preferred_word ----------

def test_pick_preferred_word_returns_first() -> None:
    assert pick_preferred_word(["determinístico", "auditable"]) == "determinístico"


def test_pick_preferred_word_skips_already_used() -> None:
    assert (
        pick_preferred_word(["determinístico", "auditable"], already_used=["determinístico"])
        == "auditable"
    )


def test_pick_preferred_word_accent_insensitive_dedup() -> None:
    # ``Determinístico`` already_used should match ``determinístico`` candidate.
    assert (
        pick_preferred_word(
            ["determinístico", "auditable"], already_used=["DETERMINÍSTICO"]
        )
        == "auditable"
    )


def test_pick_preferred_word_empty_returns_none() -> None:
    assert pick_preferred_word([]) is None
    assert pick_preferred_word(["only"], already_used=["only"]) is None


# ---------- contains_forbidden ----------

def test_contains_forbidden_basic() -> None:
    text = "Esto es disruptivo y sinérgico."
    assert contains_forbidden(text, ["disruptivo", "sinergia"]) == ["disruptivo"]


def test_contains_forbidden_word_boundary() -> None:
    """``sin`` (preposition) should NOT match inside ``asintomatico``."""
    text = "Un cuadro asintomatico se descarta."
    assert contains_forbidden(text, ["sin"]) == []


def test_contains_forbidden_accent_insensitive() -> None:
    text = "Es una experiencia inigualable."
    assert contains_forbidden(text, ["experiencia inigualable"]) == [
        "experiencia inigualable"
    ]


def test_contains_forbidden_returns_empty_for_clean_text() -> None:
    assert contains_forbidden("nada que decir.", ["disruptivo"]) == []


# ---------- matches_bad_example_pattern ----------

def test_matches_bad_example_basic_bigram_hit() -> None:
    text = "Hicimos un hilo motivacional sobre productividad."
    hits = matches_bad_example_pattern(
        text, ["Hilo motivacional sobre el futuro del marketing."]
    )
    assert len(hits) == 1


def test_matches_bad_example_does_not_fire_on_unrelated_text() -> None:
    text = "Pipeline determinístico con auditoría."
    hits = matches_bad_example_pattern(
        text, ["Hilo motivacional sobre el futuro del marketing."]
    )
    assert hits == []


def test_matches_bad_example_handles_empty_inputs() -> None:
    assert matches_bad_example_pattern("", ["x y"]) == []
    assert matches_bad_example_pattern("text", []) == []
