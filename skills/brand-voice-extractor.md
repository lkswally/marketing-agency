---
skill_id: brand-voice-extractor
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - sample_texts: list[str]
  - brand_id: str
outputs:
  - brand_voice: BrandVoice
used_by: [brand-strategist, copywriter]
---

# brand-voice-extractor

## What
From a list of brand-authored sample texts, infer the brand's `tone_words`,
`lexicon_do` (preferred vocabulary), `lexicon_dont` (avoided vocabulary),
and `banned_words`.

## When
- W1.strategy first capture of brand voice.
- Whenever copywriter needs a fresh voice read on new samples.

## Heuristics
- Tone words: 3–7 adjectives.
- Lexicon do/dont: words that appear / are conspicuously absent in samples.
- Banned words: words present in the brief's "avoid" list, never inferred
  from absence alone.

## Failure modes
- Too few samples (< 3) → return empty BrandVoice with a `confidence: low`
  notes flag at the caller's level.
- Translated samples can mislead (preserve original language).

## Out of scope
- Visual identity (palette, type).
- Tone over time (drift detection).
