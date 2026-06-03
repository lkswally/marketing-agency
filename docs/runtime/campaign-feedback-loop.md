# Runtime — Campaign Feedback Loop (MKT-6B)

Converts the deterministic analytics recommendations (MKT-6A)
into a client-facing **CampaignFeedbackPack** with suggested
tasks, channel adjustments, content suggestions, SEO / email /
social recommendations and an executive summary.

**No automatic campaign mutation.** The pack contains
suggestions only; a human reviews and decides.

- **Module:** `core/feedback/`
- **Contract:** `campaign-feedback-pack.v1`
- **CLI:** `mkt feedback-plan --client <slug>`
- **Memory kind:** `campaign_feedback_pack` (singleton: `current`)

## Quick start

```bash
# Pre-requisites: a campaign + analytics imports + analysis.
mkt run-campaign --intake examples/intake/demo-business.json
mkt build-tasks  --client acme-bootstrapped
mkt import-metrics --client acme-bootstrapped --file ga4.csv          --source ga4
mkt import-metrics --client acme-bootstrapped --file sc.csv           --source search_console
mkt import-metrics --client acme-bootstrapped --file social.csv       --source social
mkt import-metrics --client acme-bootstrapped --file email.csv        --source email
mkt analyze-metrics --client acme-bootstrapped

# Build the feedback pack.
mkt feedback-plan --client acme-bootstrapped
```

Two files land in `--outputs-dir`:

| File                          | Audience      |
|-------------------------------|---------------|
| `campaign-feedback-pack.md`   | client + team |
| `campaign-feedback-pack.json` | future sync   |

## What the pack contains

1. **Executive summary** — headline + 2-3 short paragraphs + a
   suggested agenda for the client review meeting.
2. **Stats** — counts per section.
3. **Channel adjustments** — promote best channel to HIGH, demote
   worst channel to PAUSE. When a strategy report is available,
   the planner reads `current_priority` from it.
4. **Content suggestions** — `repeat` the top performer, `improve`
   the mid-tier, `pause` pieces on the worst channel.
5. **SEO recommendations** — one per opportunity from the
   analytics layer, with priority derived from
   `opportunity_score`.
6. **Email recommendations** — derived from the metrics snapshot
   (`opens / sent`, `clicks / sent`). Low open rate → A/B test
   subject; low click rate → re-trabajar CTA.
7. **Social recommendations** — derived from the metrics snapshot
   (engagement / impressions). Below threshold → reformular hook.
8. **Suggested tasks** — one task per analyzer recommendation
   (shape mirrors MKT-4E `ExecutionTask`) plus a
   "import next cycle metrics" measurement task, plus SEO-specific
   content tasks for the top 2 SEO opportunities.
9. **Meeting agenda** — short list of decisions to bring to the
   client.

## Required vs optional inputs

| Source                            | Required? | What it contributes                  |
|-----------------------------------|-----------|--------------------------------------|
| OptimizationRecommendationPack    | ✅        | Drives every recommendation kind.    |
| MetricsSnapshot                   | optional  | Per-campaign email / social signals. |
| CampaignRunSummary                | optional  | Run id reference + summary headline. |
| CampaignExecutionTaskPack         | optional  | Task pack id reference.              |
| CreativeAssetPack                 | optional  | Per-piece content suggestions.       |
| VisualDirectionPack               | optional  | Visual pack id reference.            |
| CampaignStrategyReport            | optional  | Channel `current_priority` mapping.  |

Without the recommendation pack the CLI exits with code 2.
Without any of the others, the planner still works — it just
emits fewer cross-references.

## Cardinal guarantees (test-pinned)

- **No HTTP** — planner + renderer source grep-asserted to not
  import `requests`, `httpx`, `urllib.request`, `anthropic`.
- **No env var read** — `os.environ` absent from both modules.
- **No credential / URL field on any model** — test rejects
  `token`, `api_key`, `secret`, `credential`, `url`,
  `webhook_url`.
- **No automatic mutation** — the planner reads upstream packs
  but never writes back to them.
- **Pure planner** — same inputs → same suggestion counts
  (modulo fresh ids + timestamps).
- **Audit trail** — every `feedback-plan` run emits a `note`
  event; hash chain stays valid.

## Smoke verification

End-to-end against the demo intake + analytics fixtures:

```
total_items: 17
high_priority_tasks: 5
suggested_tasks: 9 (4 from recommendations + 1 measurement + 2 SEO + 2 more)
channel_adjustments: 2 (linkedin → HIGH, x → PAUSE)
content_suggestions: 2 (1 repeat + 1 improve)
seo_recommendations: 3
email_recommendations: 1
social_recommendations: 0
```

## CLI exit codes

| Code | Meaning                                                 |
|------|---------------------------------------------------------|
| 0    | Pack built successfully.                                |
| 2    | No OptimizationRecommendationPack — run analyze first.  |

## What's NOT in MKT-6B

- No automatic application of suggestions (no task injection
  into the execution task pack, no strategy mutation).
- No real Notion / n8n sync (those are upstream blocks already
  shipped).
- No LLM enrichment of the executive summary.
- No multi-period comparison (next cycle vs prev cycle).
- No client portal / dashboard.

## Follow-ups (PENDING.md → P-6B.*)

- `P-6B.1`: Auto-promote suggested tasks into the next
  `CampaignExecutionTaskPack` build (opt-in flag).
- `P-6B.2`: LLM-enriched executive summary using the MKT-4B
  invoker pattern.
- `P-6B.3`: Multi-period comparison (this cycle vs previous
  cycle) — requires P-6A.3 first.
- `P-6B.4`: Strategy report mutation — propose explicit
  diff to the `CampaignStrategyReport.channel_recommendation`
  and `keyword_plan` sections.
- `P-6B.5`: Customisable channel-priority thresholds in
  per-tenant config (mirrors P-6A.4).
- `P-6B.6`: Audit-trail bump to `audit-trail.v2`.
