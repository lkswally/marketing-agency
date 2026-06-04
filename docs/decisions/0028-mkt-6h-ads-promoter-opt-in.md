# ADR 0028 — MKT-6H: Ads Feedback Promoter Opt-in

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-6H
- **Supersedes:** —
- **Contract:** none new — the promoter only writes into existing
  pack contracts (`campaign-feedback-pack.v1`,
  `campaign-execution-task-pack.v1`,
  `next-campaign-iteration-plan.v1`).

## Context

After MKT-6G shipped the `AdsFeedbackBridgePack` as a standalone
deliverable, the natural ask was a way to feed it back into the
three packs that drive the operational cycle (feedback / task /
iteration). The user's hard constraint, repeated three times: no
automatic mutation. Without an explicit flag, every CLI must be
byte-compatible with the pre-MKT-6H baseline.

## Decision

### D-28.1 — Separate module `core/ads_promoter/`

Parallel to `core/ads_feedback/`. The promoter imports from
`core.ads_feedback.models`, `core.feedback.models`,
`core.execution.models`, `core.iteration.models` and never from
the planners themselves. Three pure functions plus an
`AdsPromoter` aggregator class.

Rejected alternative: extend each planner (`FeedbackPlanner`,
`TaskFactory`, `IterationPlanner`) with a `include_ads_bridge`
constructor argument. That would (a) couple the planners to the
ads bridge contract and (b) make byte-compat-without-flag harder
to prove. Keeping the promoter out-of-band — invoked only by the
CLI handlers when the flag is set — guarantees the planners
themselves stay untouched.

### D-28.2 — Three CLI handlers gain `--include-ads-bridge`

`mkt feedback-plan`, `mkt build-tasks`, `mkt apply-feedback`.
The flag defaults to `False`. When `True`, the handler:

1. Calls the planner as before.
2. Tries to load the persisted `AdsFeedbackBridgePack` via
   `_load_ads_bridge_pack_or_none` helper.
3. If the bridge pack does not exist → flag is a no-op
   (no promotion, no audit event).
4. If it exists → calls the matching `promote_into_*` function
   and emits one audit event documenting counts.
5. Persists + renders the (possibly augmented) pack.

### D-28.3 — Provenance encoded in evidence_refs / notes

Every promoted entry carries three markers:

- `ads_bridge:<pack_id>` — back-ref to the bridge pack.
- `ads_bridge_source:<source_id>` — per-source-item id, the
  dedup key.
- `origin:ads_bridge` — sentinel string.

`SuggestedTask`, `ChannelAdjustment`, `ContentSuggestion`,
`IterationAction`, `SuggestedIterationTask` all have
`evidence_refs: list[str]`. `ExecutionTask` has no
`evidence_refs` field but has `notes: str | None` — the promoter
encodes the same markers there, pipe-separated, prefixed with
the sentinel.

### D-28.4 — Idempotence via marker scan

Re-running `--include-ads-bridge` is a no-op on the second run
because the promoter, before appending, walks the existing
target-pack items and collects all `ads_bridge_source:<id>`
markers it finds. Each source item is skipped when its marker
is already present. The `PromotionResult` carries
`duplicates_skipped` so the audit event records the no-op.

Pinned by `test_*_is_idempotent` (one per surface).

### D-28.5 — Stats are recomputed after promotion

`CampaignFeedbackPack.stats` and
`NextCampaignIterationPlan.stats` carry concrete counts. The
promoter recomputes them after appending so the persisted JSON
matches the lists. `CampaignExecutionTaskPack` exposes counts
via computed properties so no explicit recompute is needed
there.

### D-28.6 — Mapping tables as module constants

`_REC_TO_FEEDBACK_TASK_CATEGORY`,
`_REC_TO_EXECUTION_CATEGORY`,
`_REC_PRIORITY_TO_*_PRIORITY`,
`_ADJ_TO_ITERATION_KIND`,
`_REC_TO_CONTENT_SUGGESTION_KIND` — all module-level dicts so
they're testable, diff-able, easy to evolve when downstream
enums grow.

### D-28.7 — `ContentSuggestion` only fires with `content_ref`

A `ContentSuggestion` (MKT-6B) targets a specific piece. The
promoter only emits one when the source recommendation carries a
`content_ref`. Otherwise the `SuggestedTask` is the sole vessel.

### D-28.8 — Promoted `ChannelAdjustment.channel == "google_ads"`

Every ads bridge campaign adjustment becomes a `google_ads`
channel adjustment in the feedback pack — the channel name
matches the snapshot's `MetricSource.GOOGLE_ADS` channel slug so
downstream analyses can group them.

### D-28.9 — Audit event payload `ads_bridge_promotion`

Wrapped in `note` envelope; carries `target`, `bridge_pack_id`,
all `PromotionResult` counts. Native envelope tracked as P-6H.5.

### D-28.10 — Read-only over the bridge pack

The promoter only reads the bridge pack. Pinned by
`test_promoter_does_not_mutate_bridge_pack` (round-trip JSON
comparison).

### D-28.11 — No Google Ads SDK reference anywhere

The promoter imports nothing from Google. The only network-side
concern is the ads bridge pack JSON. Pinned by
`test_no_google_ads_sdk_reference_in_promoter_source`.

### D-28.12 — Byte-compat without the flag

The three CLI handlers gate the promoter behind
`getattr(args, "include_ads_bridge", False)`. Without the flag,
the handler never imports `core.ads_promoter`. The persisted
JSON is byte-identical to the pre-MKT-6H output. Pinned by
`test_*_without_flag_does_not_promote` (one per CLI).

## Consequences

### Positive

- Operator can fold ads insights into the canonical operational
  packs with one flag — no manual JSON-stitching.
- Provenance markers make filtering and auditing trivial.
- Idempotent — safe to re-run after every bridge regeneration.
- Zero impact on existing planners / factories / pipelines.
- Hard byte-compat guarantee preserved.

### Negative / accepted trade-offs

- The promoter encodes provenance on `ExecutionTask.notes` (no
  evidence_refs field on that model). Operators reading raw
  notes see the marker prefix; tooling can parse it.
- `ContentSuggestion` requires `content_ref` — recommendations
  without one (rare) produce only a task. Documented in D-28.7.
- `AdsKeywordProposal` promotion is deferred (P-6H.1) until
  search-term data lands (P-6E.1).
- Audit envelope still wrapped in `note`.

## Out of scope (explicit)

- Any mutation of Google Ads state.
- Selective promotion (subset filtering, dry-run preview).
- Cross-task `depends_on` graph linking.
- Multi-source promotion.

## Validation

- 17 unit tests for the promoter module
  (`tests/ads_promoter/test_promoter.py`).
- 9 integration tests covering all three CLIs
  (`tests/cli/test_cli_include_ads_bridge.py`) — without-flag
  byte-compat, with-flag promotion, no-bridge-pack no-op,
  idempotence, audit recording.
- Total 26 new tests.
- Full suite: green.
- Ruff: clean.
- ATLAS core: untouched.

## Related

- Builds on MKT-6G (`AdsFeedbackBridgePack`), MKT-6B
  (`CampaignFeedbackPack`), MKT-4E
  (`CampaignExecutionTaskPack`), MKT-6C
  (`NextCampaignIterationPlan`).
- Future work tracked as `P-6H.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/ads-bridge-promoter.md`.
