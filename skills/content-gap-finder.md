---
skill_id: content-gap-finder
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - client_slug: str
  - client_content_topics: list[str]
  - competitors: list[Competitor]
outputs:
  - gaps: list[ContentGap]
used_by: [market-intelligence-agent]
---

# content-gap-finder

## What
Identifies topics competitors cover that the client does not, scored by a
`gap_score` (0–100) combining search interest and competitor coverage breadth.

## When
- As part of the market intelligence pack generation.
- When the content strategist needs fresh topic ideas.

## Heuristics
- Gap score = (competitor_coverage_count / total_competitors * 50)
             + (trend_relative_interest / 100 * 50).
- Only surface gaps where `gap_score >= 30`.
- `recommended_format` is inferred from the most common format among
  competitors covering that topic (e.g. if 3/4 use "blog post", suggest blog).

## Failure modes
- No competitor data → return empty gap list with note.
- No trend data → compute score from coverage only (halved scale).

## Out of scope
- Keyword difficulty / SEO competition scoring (future SEO skill).
- Backlink gap analysis (out of scope for MKT-10X).
