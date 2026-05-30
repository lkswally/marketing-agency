# ADR 0011 — MKT-3C: Creative Factory Pack

- **Status:** Accepted
- **Date:** 2026-05-30
- **Block:** MKT-3C
- **Supersedes:** —
- **Contracts:** `creative-pack.v1` (new, Pydantic, in `core/creative/models.py`).

## Context

MKT-3A produces a strategic deliverable (the 20-section markdown report).
MKT-3B produces an audit (the Approval Pack with detections and a state
machine). What was missing was the **operational** layer the creative
team consumes: structured assets with A/B variants, dates per piece,
per-piece state, per-piece checklists.

MKT-3C delivers that layer. It is deterministic, LLM-free, and
strictly non-publishing: no image is generated, no email is sent, no
post is shipped. The pack is a request for human review; downstream
publishers (post-MKT-MCP-8) will turn it into actions.

## Decision

### D-11.1 — Deterministic templates, no LLM

Same posture as MKT-3A / MKT-3B. The factory composes assets from
declared templates (hook angles, CTA styles, subject styles, headline
styles) parameterised by the strategy report. Promotion to LLM-backed
generation is a separate block that requires the safety boundaries in
`docs/runtime/agent-backend-safety.md`.

Trade: variants are deterministic and not contextually witty. The
shape (axes, counts, A/B labels, calendar) is what's fixed; the next
generator swaps in without changing the data model.

### D-11.2 — `core/creative/` is its own package

Distinct from `core/strategy/` and `core/approval/`. Three packages,
three responsibilities:

- `core/strategy/` → strategic deliverable (one per campaign).
- `core/approval/` → compliance audit + approval lifecycle.
- `core/creative/` → operational asset pack the team picks up.

Each consumes the prior layer's output but does not own the prior
layer's data model. Strategy → approval → creative is the canonical
flow.

### D-11.3 — Per-asset state is **derived**, not authored

The factory does not invent state per asset. It applies a single
derivation rule from the Approval Pack (and a conservative default
when no pack is present):

| Condition | State |
|-----------|-------|
| `blocks_publish=True` | `BLOCKED` |
| `state=APPROVED` AND not blocking | `READY_FOR_PUBLISH` |
| Severity in {risky, unsafe}, not approved | `BLOCKED` (via blocks_publish) |
| Caveat-only / safe, not approved | `DRAFT` |
| No Approval Pack persisted | `NEEDS_REVIEW` |

Centralising the rule in `_derive_state_for_assets` makes the policy
single-source.

### D-11.4 — `blocks_publish=True` propagates to ALL assets as `BLOCKED`

No override at the asset level. If the audit decided the campaign
blocks publication, every individual piece is blocked. This is policy,
not flexibility.

Rationale: per-asset overrides invite "let me ship just this one"
bypasses. The right way to unblock is to fix the upstream claims and
re-audit.

### D-11.5 — Variants are deterministic A/B rotations

Two variants per axis. IDs `A` and `B`. Each variant carries a tagged
angle/style so a future analytics layer can attribute outcomes.

Two is the minimum useful for A/B testing. Three would multiply
combinations without proportional analytical benefit at this stage.

### D-11.6 — Calendar is at the **piece** level

MKT-3A's `CampaignSchedule` is channel-level cadence ("LinkedIn: 3
posts / week"). The creative pack's calendar is asset-level dates
("post `<id>` ships Tuesday June 9").

Both coexist: the report's calendar is strategic, the pack's calendar
is operational.

### D-11.7 — Singleton id `"current"` per client

One creative pack at a time per client. Re-runs overwrite. Versioning
is a future block (same trade-off as MKT-3A and MKT-3B).

### D-11.8 — The pack references both upstream artifacts

`approval_pack_id` is optional but recorded when present. When the
factory is called without an Approval Pack, it conservatively assumes
"not yet approved" and pins state to `NEEDS_REVIEW`. The pack still
records `approval_pack_id=None` so the absence is auditable.

### D-11.9 — Audit events wrapped in `note` with action discriminator

Same pattern as MKT-3B (ADR 0010 D-10.8). Payload key
`creative_pack.action ∈ {created, updated}`. A future `audit-trail.v2`
bump may promote `approval_pack_*` and `creative_pack_*` to first-class
event types in one motion.

### D-11.10 — Image prompts include negative prompts and palette

`ImagePromptAsset.negative_prompt` ships defaults that exclude common
failure modes (handshakes, watermarks, competitor logos, purple
gradients). Palette and accessibility notes are propagated from the
strategy report's creative brief.

Rationale: the prompts must be ready-to-paste into any image generator
without further editing. Stripping safety hints would force the
operator to rebuild them each time.

### D-11.11 — Checklist is per-asset, not global

The Approval Pack's checklist is macro ("revise claims sensibles"). The
creative pack's per-asset checklist is operational ("revisar tono y
voz en este social post (LinkedIn)"). Both coexist: the pack's
checklist is a campaign-level gate; the per-asset checklist is the
day-of-production gate.

### D-11.12 — `PUBLISHED` does not exist as an asset state

The enum has `DRAFT`, `NEEDS_REVIEW`, `READY_FOR_PUBLISH`, `BLOCKED`.
Tests pin the absence of `PUBLISHED` as a contract invariant.

A future publisher will write a separate `PublicationLog` entity and
NOT mutate the pack. The pack records intent; the log records action.

### D-11.13 — `--require-approval` CLI flag fails fast

`mkt build-creatives --require-approval` exits with code 3 when the
Approval Pack blocks publish. The pack is still built; the exit code
signals an ops-level "do not proceed". Without the flag, the command
exits 0 regardless of severity (the pack itself encodes the policy).

Rationale: ops scripts can use `--require-approval` to short-circuit
pipelines; interactive users use the no-flag form to see the report.

### D-11.14 — Three flyer formats by default (1:1, 4:5, 9:16)

Covers Instagram feed, LinkedIn feed and Story / 9:16 OOH. Landscape
16:9 is supported by the enum but not generated by default — most
agency outputs do not need it at the start.

Rationale: shipping three is enough to cover the most common channels
without overproducing.

## Alternatives considered

- **LLM-backed copy generation now.** Rejected — D-11.1.
- **Single `core/marketing/` mega-package** with strategy + approval +
  creative. Rejected — the three responsibilities evolve at different
  paces and the layered package boundaries make that explicit.
- **Per-asset state authored, not derived.** Rejected (D-11.3) — invites
  drift between the pack's stance and the audit's stance.
- **Override `blocks_publish` per asset.** Rejected (D-11.4) — bypass
  vector.
- **Three or four variants per axis.** Rejected (D-11.5) — combinatoric
  explosion with no analytical payoff at this stage.
- **Add `PUBLISHED` to the state enum** with a comment "set by the
  publisher". Rejected (D-11.12) — publishers should write a separate
  log, not mutate the pack.
- **Schedule calendar by random date selection** to "feel natural".
  Rejected — determinism beats verisimilitude. Same inputs must produce
  same outputs.

## Consequences

- The creative team has a real working artifact, not a Markdown-only
  deliverable.
- Future publishers have a precise input shape with explicit policy
  flags. The contract `creative-pack.v1` is the surface they will
  consume.
- A future LLM-backed variant generator swaps in by replacing
  `_hook_variants_for_post` etc.; the model layer and the calendar are
  unchanged.
- An operational pipeline can be:
  ```
  mkt run-strategy --audit && mkt build-creatives --client <slug> --require-approval
  ```
  with the right exit codes at each step.
- The "no publish" guarantee is encoded in the type system, not just in
  policy.

## Out of scope for MKT-3C

- LLM-backed copy generation.
- Real image generation.
- ICS / Google Calendar export.
- Versioned packs (history / diff).
- Per-channel format adaptation beyond the three flyer formats.
- Actual publishing of any asset.
- A `mkt creative diff` / `preview` / `publish` CLI surface.
- Per-pack outcome tracking (A vs B winner).
- Workflow-level integration with W7 (the strategy workflow). The
  creative pack is built post-hoc, not as a phase of W7.
