# Runtime — Feedback Apply / Next Campaign Iteration Plan (MKT-6C)

Converts the persisted **CampaignFeedbackPack** (MKT-6B) into a
concrete plan for the NEXT campaign cycle: explicit actions
(repeat / pause / improve / create new), channel priority
changes, new content ideas, A/B test hypotheses, a suggested
calendar and a client-facing executive summary.

**Cardinal rule: the plan never applies changes.** It proposes
the next iteration. A human reviews and decides. No upstream
pack (strategy, creative, visual, task pack, feedback pack) is
mutated. No external API. No publishing. No LLM.

- **Module:** `core/iteration/`
- **Contract:** `next-campaign-iteration-plan.v1`
- **CLI:** `mkt apply-feedback --client <slug>`
- **Memory kind:** `next_campaign_iteration_plan` (singleton:
  `current`)

## Quick start

```bash
# Pre-requisites: a complete campaign + analytics + feedback
mkt run-campaign --intake examples/intake/demo-business.json
mkt build-tasks  --client acme-bootstrapped
mkt import-metrics --client acme-bootstrapped --file ga4.csv --source ga4
# (and the other 3 sources)
mkt analyze-metrics --client acme-bootstrapped
mkt feedback-plan  --client acme-bootstrapped

# Build the iteration plan.
mkt apply-feedback --client acme-bootstrapped
```

Two files land in `--outputs-dir`:

| File                                | Audience      |
|-------------------------------------|---------------|
| `next-campaign-iteration-plan.md`   | client + team |
| `next-campaign-iteration-plan.json` | future tooling |

## Sections (mapping 1:1 to the spec)

| Section                | Source                              |
|------------------------|-------------------------------------|
| `executive_summary`    | Derived from action counts + headline |
| `actions`              | Content suggestions + channel adjustments from feedback pack |
| `new_content_ideas`    | SEO recs (→ articles), best channel (→ social), email recs (→ email drafts) |
| `ab_test_hypotheses`   | Email recs (subject), social recs (hook), or channel promotion (format) |
| `calendar`             | Week-by-week rotation across non-paused channels, seeded by repeat/improve/create actions |
| `suggested_tasks`      | Promoted from feedback pack's tasks + measurement task |

## Action types

- `repeat_piece` — repeat a winning piece (from feedback REPEAT).
- `improve_piece` — iterate a mid-tier piece (from feedback IMPROVE).
- `pause_piece` — pause a low performer (from feedback PAUSE).
- `create_new` — create a new piece (currently not auto-generated,
  reserved for future use).
- `channel_promote` — bump a channel to HIGH priority next cycle.
- `channel_pause` — pause a channel at least one cycle.

## A/B test surfaces

- `email_subject` — when feedback has email recommendations.
- `social_hook` — when feedback has social recommendations.
- `<channel>_format` — fallback when neither email nor social recs
  exist but a channel was promoted.

Each hypothesis carries:
- `variant_a` (control)
- `variant_b` (proposed change)
- `success_metric` (open_rate / engagement_rate / ...)
- `success_threshold` (free-form, e.g. `"uplift >= 20% sobre control"`)

## Calendar rotation

The planner rotates through channels that the feedback pack did
NOT mark for pause:

1. Channels with `CHANNEL_PROMOTE` adjustments lead the rotation.
2. Channels from `CampaignStrategyReport.channel_recommendation`
   come next, skipping any in `pauses`.
3. Default fallback: `[newsletter, blog, linkedin]`.

Each week is seeded with one of the repeat/improve/create actions
when the pool is non-empty, so the calendar entry shows what
piece type to schedule.

Duration is taken from the strategy's `duration_weeks` when
available (clamped 2..12), defaulting to 4 weeks.

## Cardinal guarantees (test-pinned)

- **No HTTP** — planner + renderer source grep-asserted to not
  import `requests`, `httpx`, `urllib.request`, `anthropic`.
- **No env var read** — `os.environ` absent from both modules.
- **No credential / URL field on any model** — test rejects
  `token`, `api_key`, `secret`, `credential`, `url`,
  `webhook_url`.
- **No automatic mutation** — `test_planner_does_not_modify_upstream_packs`
  reads the feedback pack JSON before and after `plan()` and
  asserts they're equal.
- **Pure planner** — same feedback pack → same action / idea /
  calendar counts.
- **Audit trail** — every `apply-feedback` run emits a `note`
  event; hash chain stays valid.

## Smoke verification

End-to-end against the demo intake + analytics fixtures:

```
total_items: 30
total_actions: 4 (1 repeat + 1 improve + 0 pause + 0 create + 2 channel adj)
new_content_ideas: 5
ab_test_hypotheses: 1
calendar_entries: 10
suggested_tasks: 10
```

## CLI exit codes

| Code | Meaning                                                 |
|------|---------------------------------------------------------|
| 0    | Plan built successfully.                                |
| 2    | No `CampaignFeedbackPack` — run `mkt feedback-plan` first. |

## What's NOT in MKT-6C

- No automatic application of any suggestion to upstream packs.
- No LLM-enriched executive summary.
- No real Notion / n8n write (those are upstream blocks already
  shipped behind opt-in flags).
- No multi-cycle comparison.
- No new content generation (the planner suggests ideas; the
  copywriter writes them in the next campaign).
- No publishing, email send, image generation.

## Follow-ups (PENDING.md → P-6C.*)

- `P-6C.1`: Promote `SuggestedIterationTask` items into the next
  `CampaignExecutionTaskPack` via `mkt build-tasks
  --apply-iteration-plan` (opt-in flag).
- `P-6C.2`: LLM-enriched executive summary using the MKT-4B
  invoker pattern.
- `P-6C.3`: `create_new` action kind populated with actual title
  + outline ideas (currently reserved but not emitted).
- `P-6C.4`: Calendar diff vs the previous cycle's iteration plan
  (compare week-by-week shifts).
- `P-6C.5`: Strategy report mutation hints — propose explicit
  diffs to `channel_recommendation.priority` and `keyword_plan`
  sections (advisory only).
- `P-6C.6`: Audit-trail bump to `audit-trail.v2`.
