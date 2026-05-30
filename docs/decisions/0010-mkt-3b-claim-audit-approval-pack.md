# ADR 0010 — MKT-3B: Claim Audit + Approval Pack

- **Status:** Accepted
- **Date:** 2026-05-30
- **Block:** MKT-3B
- **Supersedes:** —
- **Contracts:** `approval-pack.v1` (new, Pydantic, in `core/approval/models.py`).
- **Resolves:** P-3A.3 (claim audit enforcement on the strategy report).
  Partially addresses P-3A.4 (approval halt-and-wait still needs the
  Approval Center implementation).

## Context

MKT-3A delivered the deterministic Campaign Strategy Engine. The reports
it produces are template-driven and conservative, but real campaigns
written by humans (or by future LLM-backed generators) will inevitably
include risky language — guarantees, comparatives, urgency, medical or
financial promises.

MKT-3B introduces the layer that catches those before anything ships.
It also produces the artifact a future Approval Center will consume.

## Decision

### D-10.1 — The auditor is rules-based and deterministic

Pattern-based regex rules + structural field walking. No LLM. Same
safety posture as MKT-3A: no spawn, no API, no credentials.

Trade: regex can miss paraphrases an LLM would catch. Promotion to
LLM-augmented detection is a separate block. Until then, the
deterministic rules are the regression baseline.

### D-10.2 — `core/approval/` is its own package

Distinct from `core/strategy/`. Rationale:

- Approval is a *transversal* concern. The same auditor + pack shape
  will eventually apply to other outputs (campaign drafts, asset packs,
  monthly reports).
- Separation keeps the strategy engine focused. A future redesign of
  the strategy module does not affect approval semantics.

### D-10.3 — Reuse `ClaimSeverity` / `ClaimVerdict` from MKT-1C

`approval-pack.v1` does NOT introduce new severity values. It reuses
the `safe` / `caveat` / `risky` / `unsafe` vocabulary established by
`claim-audit.v1`. New rules pick from the existing set.

This keeps the audit-trail meanings stable across the codebase.

### D-10.4 — `ApprovalState` is a 4-state subset of the Approval Center spec

`DRAFT → NEEDS_REVIEW → APPROVED | REJECTED`.

The Approval Center (`docs/approval-center.md`) defines a 5-state
machine including `NEEDS_REVISION`. The MKT-3B pack is a *contributor*
to the Approval Center; it ships in a leaner state model and the
mapping to the formal machine is documented (D-10.4 table in the runtime
doc).

Rationale: a richer state machine inside `core/approval/` would
duplicate the Approval Center's responsibilities. The pack is enough
state to support draft → review → decision; anything more (revisions,
sub-approvals, multi-reviewer flows) lives in the Approval Center
implementation block.

### D-10.5 — `ClaimRule` is data, not code

Each rule is a Pydantic `ClaimRule` with `pattern`, `category`,
`default_severity`, `description`, `suggested_mitigation`. The
`ClaimAuditor` compiles patterns lazily on construction.

This means:
- New rules can be added without touching `claim_auditor.py`.
- Per-client custom rule sets are possible (`ClaimAuditor(rules=...)`).
- Rules are testable in isolation.

The default rule set is identified by `default-rules.v1`. Custom rule
sets supply their own id. The `rule_set_id` is persisted on each pack
so audits are traceable to their source set.

### D-10.6 — The walker scans only high-risk fields

Hand-picked list in `_iter_high_risk_fields`:
- value proposition
- emails (subject, preview, body, CTA)
- social posts (hook, body, CTA)
- reels (hook, voiceover lines, on-screen text, CTA)
- creative briefs (copy overlay, CTA)
- executive summary
- suggested pieces (purpose only)

Schedules, audience labels, metrics, keyword negatives, etc. are
skipped on purpose. They would produce noise (e.g. matching "ahorrá
tiempo" inside an audience-pain description) with no marketing-claim
signal.

### D-10.7 — `blocks_publish` is policy-only

The boolean flag is set per pack but no publisher exists in MKT-3B to
honor it. Future publishers (n8n trigger, email send adapter, social
adapter — all post-MKT-MCP) MUST consult it before acting.

Rationale: shipping the flag now means the contract is fixed before
any publisher is wired. Future blocks add the enforcement, not the
shape.

### D-10.8 — Audit events are wrapped, not new event types

Every approval transition emits an `event_type=note` event with a
`payload.approval_pack.action` discriminator (`created`, `updated`,
`submitted`, `approved`, `rejected`). No new event types are added to
`audit-trail.v1`.

Rationale: the contract bump (`audit-trail.v2`) would be premature for
five action variants when `note` already carries arbitrary payloads.
When external integrations land (MKT-MCP-8) and emit their own events,
a single contract bump can register the whole batch.

### D-10.9 — Singleton id `"current"` for one pack per client at a time

Same convention as MKT-3A's strategy report. A new audit overwrites the
previous pack.

Versioning packs (history, comparison) is deferred to a dedicated block.
The motivation will appear when a real reviewer asks "what changed
since my last review?".

### D-10.10 — Approved packs never block publish; rejected packs always do

`APPROVED → blocks_publish=False` regardless of detection severity.
`REJECTED → blocks_publish=True` regardless.

Rationale: an approved pack means a human accepted the risks (with
their signature in `decision.reviewer`). A rejected pack must NEVER
ship — even if the severities were low — because rejection encodes
"do not publish this".

### D-10.11 — The pack persists `rule_set_id`

So future re-audits with a different rule set can be compared against
the original audit. Important when rule sets evolve.

### D-10.12 — `ApprovalPackBuilder` is the only mutation point

Pack construction, persistence, and transitions all go through the
builder. The model itself (`ApprovalPack`) is just data. This means:

- All audit events are emitted in one place.
- State transition validation lives in one place.
- Tests can verify the audit-event side effects by exercising the
  builder.

## Alternatives considered

- **LLM-backed detection now.** Rejected — same reason as MKT-3A
  D-9.1. Promotion requires the safety boundaries.
- **Extend `core/strategy/` instead of new package.** Rejected (D-10.2)
  — approval is transversal, not strategy-specific.
- **New severity enum specific to approval.** Rejected (D-10.3) —
  reuses `claim-audit.v1`.
- **Five-state machine matching Approval Center exactly.** Rejected
  (D-10.4) — overlap of responsibilities. The pack is a *contributor*
  to the Approval Center, not a substitute.
- **Audit every text field in the report.** Rejected (D-10.6) — noise
  swamps signal in fields like audience pain descriptions.
- **Promote audit events to `audit-trail.v2`.** Rejected for now
  (D-10.8) — premature contract bump.

## Consequences

- The strategy engine output can now be gated by an explicit, auditable
  pack before any external action.
- The `blocks_publish` policy is in place so future publishers
  (post-MKT-MCP-8) have a contract to honor from day one.
- A reviewer can read a single Markdown document (`approval-pack.md`)
  and decide approve / reject with full traceability.
- The pack shape is what the Approval Center implementation will
  consume. That block now has a defined input.
- Future LLM-backed detection slots in by swapping
  `ClaimAuditor(rules=...)` for an LLM-aware variant; the rest of the
  pipeline does not change.

## Out of scope for MKT-3B

- LLM-backed claim detection.
- Workflow-level halt-and-wait between `g_approval_packaged` and
  `g_approval_granted` (the dispatcher still runs through; only the
  pack records state).
- Approval Center entity (the formal `Approval` model from
  `docs/approval-center.md`).
- Per-client custom rule loading from disk.
- A `mkt approve` / `mkt reject` CLI surface (use the Python API today;
  CLI affordances are tracked in PENDING).
- Versioned packs (history / diff / rollback).
- External publishers honoring `blocks_publish` (MKT-MCP-8).
- Promotion of approval events to first-class `audit-trail.v2` types.
