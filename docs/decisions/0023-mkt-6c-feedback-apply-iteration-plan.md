# ADR 0023 — MKT-6C: Feedback Apply / Next Campaign Iteration Plan

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-6C
- **Supersedes:** —
- **Contract:** `next-campaign-iteration-plan.v1` (new, Pydantic, in
  `core/iteration/models.py`).

## Context

MKT-6B closed the loop on the analyzer side: it produces a
`CampaignFeedbackPack` with channel adjustments, content
suggestions and recommendations. What was missing was the
"now what?" — converting that pack into a concrete plan the
agency can execute in the next cycle.

MKT-6C ships that translation layer. The cardinal constraint
the user repeated: "no modificar campaña original", "no cambiar
tareas existentes", "solo proponer la próxima iteración". The
plan is suggestions only.

## Decision

### D-23.1 — New module `core/iteration/`

Parallel to `core/feedback/` and `core/analytics/`. Same
conventions: Pydantic models with `extra="forbid"`, planner
class with `plan/persist/load_latest`, dedicated renderer. Memory
kind: `next_campaign_iteration_plan`. Singleton: `current`.

### D-23.2 — Six action kinds, one priority scale

`IterationActionKind` enumerates exactly the six values the
spec called out:

| Kind                | Source from feedback pack          |
|---------------------|------------------------------------|
| `repeat_piece`      | ContentSuggestion(kind=REPEAT)     |
| `improve_piece`     | ContentSuggestion(kind=IMPROVE)    |
| `pause_piece`       | ContentSuggestion(kind=PAUSE)      |
| `create_new`        | Reserved (P-6C.3)                  |
| `channel_promote`   | ChannelAdjustment(new=HIGH)        |
| `channel_pause`     | ChannelAdjustment(new=PAUSE)       |

Priority is the standard `high/medium/low` scale.

### D-23.3 — Explicit A/B test hypotheses

Each `ABTestHypothesis` carries `surface`, `variant_a` (control),
`variant_b` (proposed), `success_metric` and `success_threshold`
(free-form, the reviewer interprets). The planner derives them
from:

- Email recommendations → `email_subject` test.
- Social recommendations → `social_hook` test.
- Fallback when neither exists but a channel was promoted →
  `<channel>_format` test.

Rejected alternative: leave hypothesis generation to the
copywriter. The explicit surface + variants + success_metric
shape gives the next cycle's brief a concrete experiment to
run, which is the whole point of closing the loop.

### D-23.4 — Calendar rotates channels respecting pauses

The planner builds a week-by-week calendar that:

1. Skips any channel in `pauses` (channels with `CHANNEL_PAUSE`
   action).
2. Leads with channels in `CHANNEL_PROMOTE` actions.
3. Falls back to `CampaignStrategyReport.channel_recommendation`
   when no promotions exist (skipping paused channels).
4. Final fallback: `[newsletter, blog, linkedin]`.

Duration comes from the strategy's `duration_weeks` (clamped to
2..12) or defaults to 4 weeks. Each week is seeded with one of
the repeat/improve/create actions when the pool is non-empty.

### D-23.5 — `SuggestedIterationTask` mirrors the feedback pack's tasks

The shape is intentionally close to MKT-4E `ExecutionTask` (and
MKT-6B `SuggestedTask`). The planner promotes each feedback task
into the iteration plan, plus adds a measurement task ("import
next cycle metrics") to keep the loop going.

This makes P-6C.1 (auto-promote into the next
`CampaignExecutionTaskPack`) a trivial shape mapping.

### D-23.6 — Required vs optional inputs

`CampaignFeedbackPack` is the only required input (CLI exits 2
without it). Every other artifact is loaded best-effort via
`_try_load`:

- `OptimizationRecommendationPack` → drives the "social_post"
  new-content idea for the best channel.
- `MetricsSnapshot` → currently unused (reserved for future
  revisions that need raw rows).
- `CampaignRunSummary` → run id reference.
- `CampaignExecutionTaskPack` → task pack id reference.
- `CreativeAssetPack` → creative pack id reference.
- `VisualDirectionPack` → visual pack id reference.
- `CampaignStrategyReport` → calendar duration + channel
  rotation seed.

### D-23.7 — Hard guarantee: no mutation of upstream packs

The planner reads upstream packs but never writes back. Pinned
by `test_planner_does_not_modify_upstream_packs` which fetches
the feedback pack JSON before and after `plan()` and asserts
they're equal.

The auto-promote block (P-6C.1) will be a separate opt-in flag
on `mkt build-tasks`, not part of this CLI.

### D-23.8 — Deterministic, LLM-free

Same conventions as MKT-6A/B. The executive summary is built
from concrete action counts using plain string assembly. No
LLM. LLM enrichment is tracked as P-6C.2.

### D-23.9 — CLI `mkt apply-feedback`

Subcommand args: `--client` (required), `--root`,
`--outputs-dir`. Exit codes: 0 (ok), 2 (no feedback pack).
Outputs: `next-campaign-iteration-plan.{md,json}` + one audit
event. Matches every other planner CLI in this codebase.

## Consequences

### Positive

- One command takes a feedback pack to a complete iteration
  plan with explicit decisions, ideas, tests, calendar, tasks
  and a client-ready summary. Deterministic, zero external calls.
- The iteration plan's `SuggestedIterationTask` shape matches
  the execution task pack so a future promotion block is a
  trivial shape mapping.
- A/B test hypotheses give the next brief a concrete experiment
  to design, with explicit success criteria.
- The calendar provides a sanity-check that the operator can
  diff against the previous cycle's calendar.

### Negative / accepted trade-offs

- `create_new` action kind is reserved but not auto-populated.
  The new-content-ideas section covers the "create new" intent
  via a different model (`NewContentIdea`) with more structure.
  Future work (P-6C.3) can populate `create_new` actions for
  pieces whose source recommendation explicitly says "create".
- The executive summary is templated. P-6C.2 may add LLM-enriched
  variants behind an opt-in flag.
- The calendar doesn't differentiate between "weeks 1-2 = launch,
  weeks 3-4 = nurture". A future revision can carry funnel-stage
  hints.
- No multi-cycle comparison ships in this block. Requires
  P-6A.3 (time-ranged snapshots) first.
- Promoting iteration tasks back into a real
  `CampaignExecutionTaskPack` is a separate block (P-6C.1).

## Out of scope (explicit)

- Mutation of any upstream pack.
- Automatic injection of suggested tasks into the next
  execution task pack.
- LLM enrichment of any section.
- Multi-cycle comparison.
- Strategy report mutation.
- Real Notion / n8n write (handled by upstream blocks).
- Publishing, email send, image generation.

## Validation

- 45 new tests (`tests/iteration/*` + `tests/cli/test_cli_apply_feedback.py`).
- Full suite: **1301 passed** (1256 from previous blocks + 45 new).
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified end-to-end on the demo intake + analytics
  fixtures: 30 items (4 actions + 5 new ideas + 1 A/B test +
  10 calendar entries + 10 suggested tasks).

## Related

- Depends on MKT-6B (feedback pack), MKT-6A (recommendation pack
  + snapshot), MKT-3* (strategy / creative / visual), MKT-3F
  (run summary), MKT-4E (task pack).
- Future work tracked as `P-6C.*` in `PENDING.md`.
- Runtime doc:
  `docs/runtime/feedback-apply-iteration-plan.md`.
