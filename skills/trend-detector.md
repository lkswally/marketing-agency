---
skill_id: trend-detector
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies:
  - google_trends (dry-run in MKT-10X; requires pytrends in future)
  - reddit (dry-run in MKT-10X; requires public Reddit API in future)
inputs:
  - client_slug: str
  - keywords: list[str]
  - lookback_days: int  # default 30
outputs:
  - signals: list[TrendSignal]
used_by: [market-intelligence-agent]
---

# trend-detector

## What
Detects rising, falling, and stable keyword trends relevant to the client's
category. Returns `TrendSignal` objects with `direction` and
`relative_interest` (0–100 Google Trends–scale).

## When
- Weekly before the executive report.
- On demand when the client asks "what topics are growing in my space?".

## Heuristics
- Prioritize `direction: rising` signals in the output.
- If no keywords provided, fall back to the client's primary product keywords
  from the strategy report.
- Minimum `relative_interest >= 20` to surface a signal (filter noise).

## Failure modes
- pytrends rate-limited → return cached signals from the previous run if
  available; otherwise return empty list with a note.
- No keywords → return empty list, surface a recommendation.

## Out of scope
- Social listening (separate future skill).
- News trend detection (future skill).
