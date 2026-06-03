# ADR 0022 — MKT-6B: Campaign Feedback Loop

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-6B
- **Supersedes:** —
- **Contract:** `campaign-feedback-pack.v1` (new, Pydantic, in
  `core/feedback/models.py`).

## Context

MKT-6A added analytics import + a deterministic recommendation
pack. The recommendations live as standalone analysis; nothing
ties them back into the next campaign cycle. MKT-6B closes the
loop: it consumes the recommendation pack (plus everything else
the campaign produced) and emits a **CampaignFeedbackPack** —
the document the agency hands to the client at the review
meeting.

The user's constraint, repeated three times: "no automatic
mutation". The pack is suggestions only; a human reviews and
decides what to apply.

## Decision

### D-22.1 — New module `core/feedback/`

Parallel to `core/analytics/`. Same conventions: Pydantic
models with `extra="forbid"`, planner class with
`plan/persist/load_latest`, dedicated renderer. Memory kind:
`campaign_feedback_pack`. Singleton: `current`.

### D-22.2 — Seven section types in the pack

Each section answers a question the spec listed:

| Section                 | Spec question                                          |
|-------------------------|--------------------------------------------------------|
| `executive_summary`     | "resumen ejecutivo para el cliente"                    |
| `channel_adjustments`   | "cambios de prioridad por canal"                       |
| `content_suggestions`   | "qué pieza repetir / pausar / mejorar"                 |
| `seo_recommendations`   | "mejoras de SEO"                                       |
| `email_recommendations` | "recomendaciones de email"                             |
| `social_recommendations`| "recomendaciones de social"                            |
| `suggested_tasks`       | "nuevas tareas operativas"                             |

Each section is a list of typed Pydantic models with
`priority`, `rationale`, `evidence_refs` (free-form back-refs
to source recommendation_ids / channel names / content_refs).

### D-22.3 — `SuggestedTask` mirrors `ExecutionTask` shape

`SuggestedTask` has `task_id`, `title`, `category`, `priority`,
`rationale`, `suggested_owner`, `channel`, `content_ref`,
`evidence_refs`. A future block (P-6B.1) can promote these
directly into the next `CampaignExecutionTaskPack` without
shape transformation.

### D-22.4 — `ChannelPriority` includes `PAUSE`

Beyond high/medium/low (matching the strategy report
convention), MKT-6B adds a fourth value: `pause`. This is the
canonical signal for "do not publish on this channel for at
least one cycle" — emitted whenever the analyzer's
`worst_channel` is non-None.

### D-22.5 — Required vs optional inputs

`OptimizationRecommendationPack` is the only required input
(CLI exits with code 2 without it). Every other artifact is
optional and consulted best-effort via `_try_load`:

- `MetricsSnapshot` → per-campaign email/social recommendations.
- `CampaignRunSummary` → run id reference for traceability.
- `CampaignExecutionTaskPack` → task pack id reference.
- `CreativeAssetPack` → per-piece pause suggestions on the
  worst channel.
- `VisualDirectionPack` → visual pack id reference.
- `CampaignStrategyReport` → `current_priority` mapping per
  channel.

This makes the planner usable in two modes:
- **Full stack** — the operator just finished the campaign
  pipeline + analytics, every cross-reference is populated.
- **Analytics-only** — the operator ran imports on an
  out-of-band dataset (e.g. metrics from a previous agency)
  before integrating with our pipeline; the pack still
  produces useful suggestions.

### D-22.6 — Email + social recommendations from snapshot

The planner aggregates the metrics snapshot per
campaign_id (for email) and per (channel, content_ref) (for
social). Three constants gate the recommendations:

- `_EMAIL_LOW_OPEN_RATE = 0.20`
- `_EMAIL_LOW_CLICK_RATE = 0.02`
- `_SOCIAL_LOW_ENGAGEMENT_PER_IMP = 0.01`
- `_SOCIAL_MIN_IMPRESSIONS = 500.0`

These mirror the analytics-layer threshold pattern from MKT-6A
and are tracked for tuning under `P-6A.4` /  `P-6B.5`.

### D-22.7 — Deterministic, LLM-free

Same conventions as the analytics analyzer. The executive
summary is built from concrete pack data (`best_channel`,
`worst_channel`, top SEO opportunity, snapshot row count) using
plain string assembly. No LLM. LLM enrichment is tracked as
P-6B.2 (opt-in, using the MKT-4B Claude invoker pattern).

### D-22.8 — Cardinal guarantee: no automatic mutation

The planner reads upstream packs but never writes back to them.
The promoter that would inject suggested tasks into the next
`CampaignExecutionTaskPack` ships separately (P-6B.1, opt-in).
This block is purely advisory.

Test-pinned: the planner module's source is grep-asserted to
contain no `requests`, `httpx`, `urllib.request`, `os.environ`,
or `anthropic`. The pack model has no `token` / `api_key` /
`secret` / `credential` / `url` fields.

### D-22.9 — CLI `mkt feedback-plan`

Subcommand args: `--client` (required), `--root`,
`--outputs-dir`. Exit codes: 0 (ok), 2 (no recommendation
pack). Outputs: `campaign-feedback-pack.md` +
`campaign-feedback-pack.json` + one audit event. Matches the
conventions of every other planner CLI in this codebase.

### D-22.10 — Renderer surfaces 9 sections + footer

Markdown sections (in order): header, executive summary, stats,
channel adjustments, content suggestions, SEO, email, social,
suggested tasks, meeting agenda, footer. Each section degrades
gracefully when empty (`_(sin ...)_`).

## Consequences

### Positive

- One command takes a finished campaign + imported analytics to
  a complete, client-ready feedback document. Deterministic,
  0 external calls.
- The pack's `SuggestedTask` shape matches the execution task
  pack so a future promotion block is a trivial shape mapping.
- The executive summary + meeting agenda turns the analysis
  into something an account lead can read aloud at the client
  call.
- Empty / partial inputs degrade gracefully — the planner is
  usable even without the full pipeline.

### Negative / accepted trade-offs

- The executive summary is templated and short; for a richer
  voice the operator either rewrites it or waits for P-6B.2's
  LLM enrichment.
- Email / social thresholds are hard-coded constants. Per-tenant
  config is P-6B.5.
- The planner does not yet compare with the previous cycle's
  pack. Multi-period comparison is P-6B.3 (requires P-6A.3's
  time-ranged snapshots).
- Strategy mutation (the analyzer says "pause x" → the next
  strategy report's channel list reflects it) is explicitly out
  of scope (P-6B.4).

## Out of scope (explicit)

- Automatic injection of suggested tasks into the execution
  task pack.
- LLM enrichment of the summary.
- Multi-cycle comparison.
- Strategy report mutation.
- Real Notion / n8n write (handled by upstream blocks).
- Email send, publishing, image generation.

## Validation

- 43 new tests (`tests/feedback/*` + `tests/cli/test_cli_feedback_plan.py`).
- Full suite: **1256 passed** (1213 from previous blocks + 43 new).
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified end-to-end on the demo intake + analytics
  fixtures: 17 items (9 tasks + 2 channel adjustments + 2
  content + 3 SEO + 1 email + 0 social), 5 high-priority.

## Related

- Depends on MKT-6A (recommendation pack + snapshot), MKT-3*
  (strategy + creative + visual), MKT-3F (run summary),
  MKT-4E (task pack).
- Future work tracked as `P-6B.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/campaign-feedback-loop.md`.
