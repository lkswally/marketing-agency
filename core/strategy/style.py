"""Style helpers for the strategy templates (MKT-4D).

Pure helpers — no I/O, no state, deterministic. Every function in this
module is unit-tested in ``tests/strategy/test_style.py``.

The module exists to centralise three categories of work that were
previously inlined in ``core.strategy.templates`` and produced known
bad output (documented in MKT-4C):

1. **Unicode-aware slugs and hashtags.** Naive ASCII strips like the
   previous ``re.sub(r"[^a-z0-9]", ...)`` turn ``Diseñado`` into
   ``diseado`` (with no ``ñ``) which then becomes a useless cluster
   label or hashtag. We use ``unicodedata.normalize("NFD", ...)`` and
   strip combining marks so ``Diseñado`` → ``disenado`` (still ugly,
   but ``ñ → n`` is the canonical fold; meaningful_keyword filtering
   then drops the cluster entirely since it's a verb tense, not a
   noun).

2. **Stopword and triviality filtering.** Spanish stopwords (``sin``,
   ``con``, ``para``, ``de``, ``el``, ``y``, etc.) and short generic
   tokens (``setup``, ``demo``) are removed before being used as the
   seed of a keyword cluster or a hashtag.

3. **Brand voice application.** The intake captures ``brand_tone``
   (list of tone words) and ``preferred_words`` (lexicon). The
   templates now use these helpers to (a) pick adjectives that match
   the tone, (b) inject preferred words naturally without forcing
   them, (c) avoid forbidden words and flag them when found.

The helpers are conservative: when a transformation would produce an
empty string or a meaningless word, they return ``None`` and the
caller falls back to a sensible default.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# ---------- Constants ----------

# Spanish stopwords. Kept small on purpose — only the tokens we actually
# see breaking through to keyword/hashtag generation in real intakes.
_ES_STOPWORDS: frozenset[str] = frozenset({
    # articles
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    # prepositions
    "a", "ante", "bajo", "con", "contra", "de", "desde", "en", "entre",
    "hacia", "hasta", "para", "por", "segun", "sin", "so", "sobre", "tras",
    # conjunctions
    "y", "e", "o", "u", "ni", "pero", "mas", "que", "si", "no",
    # pronouns / common
    "me", "te", "se", "nos", "le", "lo", "su", "sus", "mi", "tu", "yo",
    "esto", "esta", "este", "eso", "esa", "ese", "muy", "menos",
    # verbs that surface as junk seeds
    "ser", "es", "son", "sera", "fue", "estar", "estan",
    "hace", "hay", "han", "haber",
})

# Generic single tokens that produce useless clusters when used as a
# keyword seed. Different from stopwords: these are real words, just
# too generic to be a cluster on their own.
_GENERIC_NOUN_TOKENS: frozenset[str] = frozenset({
    "setup", "demo", "free", "test", "info", "data",
})

# Minimum length for a token to become a keyword cluster seed.
_MIN_KEYWORD_LEN = 4

# Maximum length of a token before we suspect it is a glued sentence.
_MAX_HASHTAG_LEN = 30


# ---------- Tone families ----------

# Tone words are arbitrary user strings. We classify them into a small
# number of families and each family carries a tuple of (adjective,
# connector, opener) used by the templates. Unknown tone words fall
# into ``neutral``.
_TONE_FAMILIES: dict[str, tuple[str, str, str]] = {
    "tecnico": ("preciso", "concretamente", "Para entrar en detalle:"),
    "tecnico-pragmatico": ("preciso", "concretamente", "Sin vueltas:"),
    "anti-marketing": ("directo", "sin floritura", "Vamos al punto:"),
    "anti-marketing-hueco": ("directo", "sin floritura", "Vamos al grano:"),
    "honesto": ("honesto", "para ser claros", "Mejor decirlo de frente:"),
    "irreverente": ("franco", "honestamente", "Pongámoslo así:"),
    "claro": ("claro", "en concreto", "Concretamente:"),
    "directo": ("directo", "sin vueltas", "Sin vueltas:"),
    "calido": ("cercano", "entre nosotros", "Te lo decimos así:"),
    "profesional": ("riguroso", "técnicamente", "Profesionalmente:"),
    "neutral": ("práctico", "en concreto", "En concreto:"),
}

# Lookup: each user tone word maps via substring match to a family key.
_TONE_KEYWORDS: list[tuple[str, str]] = [
    ("tecnico-pragmatico", "tecnico-pragmatico"),
    ("anti-marketing-hueco", "anti-marketing-hueco"),
    ("anti-marketing", "anti-marketing"),
    ("tecnico", "tecnico"),
    ("tecnica", "tecnico"),
    ("pragmatico", "tecnico-pragmatico"),
    ("honesto", "honesto"),
    ("transparente", "honesto"),
    ("irreverente", "irreverente"),
    ("provocador", "irreverente"),
    ("claro", "claro"),
    ("directo", "directo"),
    ("calido", "calido"),
    ("cercano", "calido"),
    ("amigable", "calido"),
    ("profesional", "profesional"),
    ("formal", "profesional"),
    ("riguroso", "profesional"),
]


# ---------- Unicode normalization ----------

def fold_diacritics(text: str) -> str:
    """Return ``text`` with combining marks stripped via NFD.

    Examples
    --------
    >>> fold_diacritics("Diseñado")
    'Disenado'
    >>> fold_diacritics("acción")
    'accion'
    >>> fold_diacritics("café")
    'cafe'
    """
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def normalize_for_slug(text: str) -> str:
    """Lowercase, fold diacritics, keep only ``[a-z0-9 -]``, collapse spaces.

    Returns an empty string for empty input. Never raises.
    """
    folded = fold_diacritics(text or "").lower()
    folded = re.sub(r"[^a-z0-9\s-]", "", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded


def make_hashtag(text: str) -> str | None:
    """Build a clean hashtag from ``text``. Returns ``None`` for junk input.

    Rules:
    - Fold diacritics first so ``Diseñado`` becomes ``Disenado``.
    - Title-case word tokens and concatenate.
    - Reject hashtags shorter than 3 letters or longer than 30.
    - Reject hashtags that are just a stopword.
    """
    folded = fold_diacritics(text or "").strip()
    if not folded:
        return None
    # Split on non-alphanumerics, title-case each, rejoin.
    tokens = re.findall(r"[A-Za-z0-9]+", folded)
    if not tokens:
        return None
    joined = "".join(t.capitalize() for t in tokens)
    if len(joined) < 3 or len(joined) > _MAX_HASHTAG_LEN:
        return None
    if joined.lower() in _ES_STOPWORDS:
        return None
    return "#" + joined


# ---------- Keyword filtering ----------

def is_meaningful_keyword(word: str) -> bool:
    """Return True if ``word`` is acceptable as a keyword cluster seed."""
    if not word:
        return False
    folded = fold_diacritics(word).lower().strip()
    if len(folded) < _MIN_KEYWORD_LEN:
        return False
    if folded in _ES_STOPWORDS:
        return False
    return folded not in _GENERIC_NOUN_TOKENS


def first_meaningful_token(text: str) -> str | None:
    """Return the first whitespace-split token of ``text`` that passes
    :func:`is_meaningful_keyword`, or ``None``."""
    if not text:
        return None
    for tok in text.split():
        tok = tok.strip(".,;:!?¡¿\"'()[]{}")
        if is_meaningful_keyword(tok):
            return fold_diacritics(tok).lower()
    return None


# ---------- Brand voice ----------

def _classify_tone(tone_words: Iterable[str]) -> str:
    """Map a list of tone words to a tone family key. Falls back to
    ``"neutral"`` when nothing matches."""
    folded_words = [fold_diacritics(w).lower() for w in tone_words]
    for needle, family in _TONE_KEYWORDS:
        for w in folded_words:
            if needle in w:
                return family
    return "neutral"


def tone_adjective(tone_words: Iterable[str]) -> str:
    """Return an adjective consistent with the tone family."""
    return _TONE_FAMILIES[_classify_tone(tone_words)][0]


def tone_connector(tone_words: Iterable[str]) -> str:
    """Return a sentence connector consistent with the tone family."""
    return _TONE_FAMILIES[_classify_tone(tone_words)][1]


def tone_opener(tone_words: Iterable[str]) -> str:
    """Return an opening phrase consistent with the tone family."""
    return _TONE_FAMILIES[_classify_tone(tone_words)][2]


def pick_preferred_word(
    preferred_words: Iterable[str],
    already_used: Iterable[str] | None = None,
) -> str | None:
    """Return the first preferred word not yet used, or ``None``.

    Deterministic: walks the list in declared order. Caller passes
    ``already_used`` to avoid reusing words across surfaces in the
    same surface bundle.
    """
    used_folded = {
        fold_diacritics(w).lower() for w in (already_used or ())
    }
    for w in preferred_words:
        if not w:
            continue
        if fold_diacritics(w).lower() not in used_folded:
            return w
    return None


def contains_forbidden(text: str, banned: Iterable[str]) -> list[str]:
    """Return the list of banned words found in ``text``.

    Case-insensitive and diacritic-folded match. Matches on word
    boundaries so ``sin`` does NOT match inside ``asintomatico``.
    Empty result means the text is clean.
    """
    folded_text = " " + fold_diacritics(text or "").lower() + " "
    found: list[str] = []
    for word in banned:
        folded_w = fold_diacritics(word).lower().strip()
        if not folded_w:
            continue
        if re.search(rf"\b{re.escape(folded_w)}\b", folded_text):
            found.append(word)
    return found


# ---------- Good/bad examples ----------

def matches_bad_example_pattern(text: str, bad_examples: Iterable[str]) -> list[str]:
    """Return bad-example patterns present in ``text``.

    Heuristic: each bad_example is a sentence; we extract its most
    distinctive 2-4 word token sequence and check substring presence
    (diacritic-folded, lowercased). Conservative: false negatives are
    fine, false positives would be annoying.
    """
    folded_text = fold_diacritics(text or "").lower()
    hits: list[str] = []
    for example in bad_examples:
        ex_folded = fold_diacritics(example or "").lower()
        # Distinctive 2-word seed: drop the first article+noun, look at
        # the next pair. For "Stock photos de handshakes" → "stock photos".
        toks = [t for t in re.split(r"[^a-z0-9]+", ex_folded) if t]
        if len(toks) < 2:
            continue
        # Use the first meaningful 2-token bigram.
        bigrams = list(zip(toks, toks[1:], strict=False))
        for a, b in bigrams:
            if a in _ES_STOPWORDS or b in _ES_STOPWORDS:
                continue
            if len(a) < 3 or len(b) < 3:
                continue
            needle = f"{a} {b}"
            if needle in folded_text:
                hits.append(example)
                break
    return hits


__all__ = [
    "contains_forbidden",
    "first_meaningful_token",
    "fold_diacritics",
    "is_meaningful_keyword",
    "make_hashtag",
    "matches_bad_example_pattern",
    "normalize_for_slug",
    "pick_preferred_word",
    "tone_adjective",
    "tone_connector",
    "tone_opener",
]
