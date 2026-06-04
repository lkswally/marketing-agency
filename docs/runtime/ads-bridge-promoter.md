# Ads Bridge Promoter — opt-in `--include-ads-bridge` (MKT-6H)

Runtime guide for folding the `AdsFeedbackBridgePack` (MKT-6G)
content into the canonical operational packs. **Opt-in only** —
without the flag, all three CLIs are byte-compatible with the
pre-MKT-6H baseline.

## Quick start

```bash
# Pre-req: an AdsFeedbackBridgePack exists for the client.
mkt analytics-fetch --client acme --source google_ads          # or import-metrics
mkt ads-analyze --client acme
mkt ads-feedback --client acme

# Now fold it into the three operational packs:
mkt feedback-plan   --client acme --include-ads-bridge
mkt build-tasks     --client acme --include-ads-bridge
mkt apply-feedback  --client acme --include-ads-bridge
```

If the bridge pack does not exist, `--include-ads-bridge` is a
no-op (no promotion, no audit event). Exit code stays 0.

## What the flag does

| Command           | Source items from bridge pack                                     | Target pack entries added |
|-------------------|--------------------------------------------------------------------|---------------------------|
| `feedback-plan`   | `recommendations`, `campaign_adjustments`                          | `SuggestedTask`, `ChannelAdjustment("google_ads")`, `ContentSuggestion` (when content_ref present) |
| `build-tasks`     | `recommendations`                                                  | `ExecutionTask` (state `todo`, channel `google_ads`) |
| `apply-feedback`  | `campaign_adjustments`, `suggested_tasks`                          | `IterationAction`, `SuggestedIterationTask` |

## Provenance markers

Every promoted entry carries the following on its `evidence_refs`
list (or, for `ExecutionTask`, on its `notes` string):

| Marker                                  | Meaning                                        |
|-----------------------------------------|------------------------------------------------|
| `ads_bridge:<pack_id>`                  | back-ref to the bridge pack                    |
| `ads_bridge_source:<recommendation_id>` | per-source-item id (used for dedup)            |
| `origin:ads_bridge`                     | sentinel string for fast filtering             |

Operators can filter the resulting packs for the sentinel to see
which entries came from the ads bridge.

## Idempotence

Re-running the same command with the same bridge pack is a no-op
on the second run:

1. Planner builds a fresh target pack.
2. Promoter walks the existing entries, collects all
   `ads_bridge_source:` markers it finds.
3. Each bridge item is skipped when its
   `ads_bridge_source:<id>` marker is already present.
4. The audit event records `duplicates_skipped` so operators see
   what happened.

This means you can safely run `--include-ads-bridge` after every
bridge regeneration. Old promoted entries stay; new ones land.

## Mappings — full table

### Insight kind / action → `ChannelPriority` (feedback pack)

| `AdsAdjustmentKind`   | `ChannelPriority`  |
|-----------------------|--------------------|
| `pause_review`        | `pause`            |
| `scale_review`        | `high`             |
| `reallocate_review`   | `medium`           |
| `optimize_review`     | `medium`           |

### Recommendation kind → `SuggestedTaskCategory` (feedback pack)

| Recommendation kind        | Category        |
|----------------------------|------------------|
| `pause_review`             | `optimization`   |
| `review_campaign`          | `optimization`   |
| `review_ad_group`          | `optimization`   |
| `review_landing`           | `optimization`   |
| `scale_opportunity`        | `optimization`   |
| `improve_ad_copy`          | `content`        |
| `budget_review`            | `operational`    |
| `negative_keyword_proposal`| `operational`    |

### Recommendation kind → `TaskCategory` (execution pack)

| Recommendation kind        | Category        |
|----------------------------|------------------|
| `improve_ad_copy`          | `social`         |
| All others                 | `operational`    |

### Recommendation kind → `ContentSuggestionKind` (feedback pack)

Only fires when `content_ref` is set:

| Recommendation kind   | `ContentSuggestionKind` |
|-----------------------|--------------------------|
| `pause_review`        | `pause`                  |
| `improve_ad_copy`     | `improve`                |
| `scale_opportunity`   | `repeat`                 |
| `review_landing`      | `improve`                |

### Adjustment kind → `IterationActionKind` (iteration plan)

| `AdsAdjustmentKind`   | `IterationActionKind`   |
|-----------------------|--------------------------|
| `pause_review`        | `pause_piece`            |
| `scale_review`        | `channel_promote`        |
| `reallocate_review`   | `channel_promote`        |
| `optimize_review`     | `improve_piece`          |

### Priority → priority

`AdsRecommendationPriority` maps 1:1 to each target's priority
enum (`HIGH`, `MEDIUM`, `LOW`).

## Audit trail

Each promotion run appends one event with payload
`ads_bridge_promotion`:

```json
{
  "ads_bridge_promotion": {
    "action": "promoted",
    "target": "campaign_feedback_pack" | "campaign_execution_task_pack" | "next_campaign_iteration_plan",
    "bridge_pack_id": "...",
    "recommendations_promoted": N,
    "tasks_promoted": N,
    "channel_adjustments_promoted": N,
    "content_suggestions_promoted": N,
    "iteration_actions_promoted": N,
    "duplicates_skipped": N
  }
}
```

Wrapped in `note` envelope; native `ads_bridge_promotion.v1`
envelope tracked as **P-6H.5**.

## Cardinal guarantees

- **Opt-in only.** Without `--include-ads-bridge`, the three CLI
  handlers behave exactly as they did pre-MKT-6H. The promoter
  module is not imported.
- **Read-only over the bridge pack.** The promoter only reads
  it; never writes back. Pinned by
  `test_promoter_does_not_mutate_bridge_pack`.
- **No Google Ads SDK reference.** Pinned by
  `test_no_google_ads_sdk_reference_in_promoter_source`.
- **No campaign mutation, no keyword execution, no budget edit.**
  Promoter just appends to local in-memory pack lists.
- **Idempotent.** Tested for each of the three CLIs.

## Exit codes

- `0` on success (including when the bridge pack does not exist
  and the flag is a no-op).
- `2` only on the same conditions as the underlying CLI (missing
  upstream pack for `feedback-plan` / `apply-feedback`, missing
  strategy report for `build-tasks`).

## NOT in scope (deferred — see PENDING.md)

- P-6H.1 — Promote `AdsKeywordProposal` entries into
  `CampaignFeedbackPack` (today proposals stay in the bridge pack
  only; promoting them as suggestions requires P-6E.1 search-term
  data to be meaningful).
- P-6H.2 — Filter / select subset of recommendations to promote
  (e.g. `--include-ads-bridge=high` for HIGH priority only).
- P-6H.3 — Dry-run preview of what would be promoted.
- P-6H.4 — Promote into `ExecutionTask.depends_on` graph (today
  promoted tasks are standalone).
- P-6H.5 — Native `ads_bridge_promotion.v1` audit envelope.
- P-6H.6 — Multi-source promotion (e.g. additional bridge packs
  beyond Google Ads).
