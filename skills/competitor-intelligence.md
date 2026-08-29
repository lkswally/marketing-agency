---
skill_id: competitor-intelligence
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - client_slug: str
  - competitor_urls: list[str]
  - keywords: list[str]
outputs:
  - signals: list[CompetitorSignal]
  - pack: MarketIntelligencePack
used_by: [market-intelligence-agent]
---

# competitor-intelligence

## What
Observes competitor activity (new content, pricing changes, new offers,
social activity) and returns a list of `CompetitorSignal` objects.
In MKT-10X all data comes from `DryRunCompetitorMonitor` fixtures.

## When
- Before weekly executive report generation.
- When the strategy pipeline requests a market context refresh.

## Heuristics
- Surface only `confidence: high | medium` signals in the executive report.
- Deduplicate: if the same competitor_url + observation_type already appeared
  in the current cycle, skip the duplicate.
- Never infer pricing from visual screenshots alone; mark as `confidence: low`.

## Failure modes
- External source unavailable → return empty signal list with a note; do NOT block the pipeline.
- Competitor URL unreachable → log note, continue.

## Out of scope
- Paid Ads creative scraping (use meta-ads-library adapter, separate skill).
- Social follower counts (future skill).
