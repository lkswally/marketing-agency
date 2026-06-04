# ADR 0027 — MKT-6G: Ads Insights to Feedback Loop Integration

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-6G
- **Supersedes:** —
- **Contract:** `ads-feedback-bridge-pack.v1` (new, Pydantic, in
  `core/ads_feedback/models.py`).

## Context

After MKT-6F shipped the Google Ads analyzer with structured
insights, the analyzer's output was a closed deliverable — it
didn't fold into the existing feedback / iteration packs that
drive the agency's next-cycle plan. The user asked for a bridge
that converts `GoogleAdsInsight` entries into the same idiom the
rest of the system speaks (recommendations, campaign adjustments,
suggested tasks) without ever applying anything.

The cardinal constraint repeated four times: no campaign edit,
no keyword add, no negative-keyword execution, no budget change.
Everything is a suggestion.

## Decision

### D-27.1 — Separate module `core/ads_feedback/`

Parallel to `core/ads_analysis/`, `core/feedback/`,
`core/iteration/`. Same conventions: Pydantic models, deterministic
bridge class, dedicated renderer, CLI subcommand. The bridge
module imports from `core.ads_analysis` and `core.memory` only —
no Google SDK, no HTTP libs.

Rejected: extending `CampaignFeedbackPack` directly. That pack
already mixes channel adjustments, content suggestions, SEO,
email and social recommendations. Adding Ads-specific kinds would
either bloat the union types or weaken the existing contract.
Keeping the bridge pack separate (with explicit
`feedback_pack_id` cross-reference) gives both packs the freedom
to grow.

### D-27.2 — Eight `AdsRecommendationKind` values

`pause_review`, `review_campaign`, `review_ad_group`,
`review_landing`, `scale_opportunity`, `improve_ad_copy`,
`budget_review`, `negative_keyword_proposal`. The first seven map
1:1 from `AdsInsightKind`. The eighth is reserved for the
search-term wiring (P-6E.1 / P-6F.2) — emitted today only when
an insight's evidence carries an extractable candidate, which is
zero with the current rule set.

### D-27.3 — Four `AdsAdjustmentKind` values

`pause_review`, `scale_review`, `reallocate_review`,
`optimize_review`. Maps from `AdsInsightAction`:

- `PAUSE_CANDIDATE` → `pause_review`
- `SCALE_CANDIDATE` → `scale_review`
- `BUDGET_REVIEW` → `reallocate_review`
- `REVIEW_CAMPAIGN` → `optimize_review`

Other actions (`IMPROVE_AD_COPY`, `REVIEW_AD_GROUP`,
`REVIEW_LANDING`) are ad-group level or sub-campaign level — they
don't produce a campaign adjustment.

### D-27.4 — Dedup adjustments per (campaign_id, kind)

Multiple ad-group insights on the same campaign produce
multiple recommendations but one campaign adjustment. The
operator sees the campaign-level direction once. Pinned by
`test_multiple_insights_same_campaign_dedup_adjustment`.

### D-27.5 — Tasks mirror MKT-6B `SuggestedTask` shape

`AdsSuggestedTask` mirrors `SuggestedTaskCategory` /
`SuggestedTaskPriority`. Each recommendation produces one task,
plus a trailing `measurement` task ("Review with account lead").
This makes the future P-6G.1 promoter a trivial shape mapping.

### D-27.6 — Negative-keyword proposals are persisted text

`AdsKeywordProposal.proposed_as` is locked to `negative_keyword`
in v1. There is NO positive-keyword variant. The model has no
"execute" field, no API call, no Google identifier — just the
text the operator would manually add as a negative in Ads UI.

Today the bridge emits zero proposals (no search-term data in
snapshot). The wiring is in place so P-6E.1 / P-6F.2 lands as a
no-op for this layer.

### D-27.7 — Cross-references are best-effort, never required

The bridge looks up MKT-6B feedback, MKT-4E execution task pack,
MKT-6C iteration plan. If any is missing, the corresponding field
on the bridge pack is `None`. Pinned by
`test_cross_refs_none_when_packs_missing` and
`test_cross_refs_populated_when_packs_exist`.

### D-27.8 — Read-only over upstream packs

The bridge reads `GoogleAdsInsightPack`, optionally reads three
other packs for cross-ref, and writes exactly one new artifact.
It never mutates the snapshot, the insight pack, the feedback
pack, the execution task pack or the iteration plan. Pinned by
`test_bridge_does_not_mutate_upstream_packs`.

### D-27.9 — Deterministic translation

Insight pack ordering carries over into recommendation ordering.
Two runs over the same insight pack produce the same recommendation
sequence (modulo fresh ids and timestamps). Pinned by
`test_deterministic_recommendation_ordering`.

### D-27.10 — CLI subcommand `mkt ads-feedback`

Exit 0 on success, exit 2 when no `GoogleAdsInsightPack` exists.
Outputs MD + JSON + one audit event. Same convention as every
other planner / analyzer CLI in this codebase.

### D-27.11 — Audit envelope wrapped in `note`

Same trade-off as every previous block. P-6G.7 tracks the
`ads_feedback_bridge_pack.v1` native envelope.

## Consequences

### Positive

- One CLI command bridges the Ads-specific analyzer output into
  the same idiom the rest of the feedback loop speaks.
- The pack is a clear deliverable an operator can hand the
  account team: recommendations + campaign adjustments + tasks +
  executive summary.
- Future promotion blocks (P-6G.1 / P-6G.2 / P-6G.3) are trivial
  shape mappings because the bridge already emits MKT-4E /
  MKT-6B / MKT-6C compatible shapes.
- Zero impact on existing analyzer / connectors / feedback /
  iteration / execution pipelines.
- Bridge fails loudly only when there's nothing to bridge
  (`exit 2` + missing insight pack).

### Negative / accepted trade-offs

- Negative-keyword surface is wired but produces zero proposals
  today (no search-term data). The shape is locked to give
  P-6E.1 a clean landing.
- Bridge does not auto-promote suggestions into other packs —
  opt-in only (P-6G.1 / P-6G.2 / P-6G.3). The user's "no
  automatic mutation" rule extends to inter-pack auto-merge.
- The cross-reference pack lookup is best-effort by pack id
  only — does not validate that the referenced pack still
  exists at the time the bridge is consumed.
- Audit envelope still wrapped in `note` (P-6G.7).

## Out of scope (explicit)

- Any mutation of Google Ads state.
- Auto-merge into other packs.
- Real search-term / negative-keyword extraction (needs P-6E.1).
- LLM enrichment.
- Multi-cycle comparison.

## Validation

- 39 new tests across `tests/ads_feedback/*` +
  `tests/cli/test_cli_ads_feedback.py`.
- Full suite: green.
- Ruff: clean.
- ATLAS core: untouched.

## Related

- Depends on MKT-6F (`GoogleAdsInsightPack`).
- Optionally reads from MKT-6B (`CampaignFeedbackPack`),
  MKT-4E (`CampaignExecutionTaskPack`),
  MKT-6C (`NextCampaignIterationPlan`).
- Future work tracked as `P-6G.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/ads-feedback-bridge.md`.
