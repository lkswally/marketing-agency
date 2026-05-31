# ADR 0013 — MKT-3E: Client Brief Intake Pack

- **Status:** Accepted
- **Date:** 2026-05-30
- **Block:** MKT-3E
- **Supersedes:** —
- **Contracts:** `client-intake.v1` and `intake-validation.v1` (both
  new, Pydantic, in `core/intake/models.py`).

## Context

The pipeline now produces real deliverables end to end (strategy,
audit, creative, visual). The only friction left was the entry point:
the human had to hand-write a `StrategyInputBrief` JSON that matched
the internal Pydantic shape exactly, with no validation, no defaults,
no warnings about missing fields.

MKT-3E adds the **first mile**: a friendly, permissive intake shape
that a human (or an upstream form) can fill, plus a deterministic
validator and normalizer that produce the canonical
`StrategyInputBrief` and surface missing fields.

The cardinal constraint, set explicitly by the user, is that the
intake layer **never invents data**. Missing fields are reported, not
filled.

## Decision

### D-13.1 — Deterministic, no LLM, no scraping

Same posture as MKT-3A through MKT-3D. The validator is rule-based;
the normalizer is a pure mapping function. Promotion to
LLM-assisted intake completion is a separate block that requires the
safety boundaries from `docs/runtime/agent-backend-safety.md`.

### D-13.2 — `core/intake/` is its own package

Alongside `core/strategy/`, `core/approval/`, `core/creative/`,
`core/visual/`. Intake is conceptually the first mile (human → typed
data); strategy/approval/creative/visual are the downstream
pipeline. Keeping intake separate lets it evolve independently
(e.g. a future web form would land here without touching downstream
layers).

### D-13.3 — `ClientIntake` is permissive, validator decides severity

Only `client_name` is required by the model. Every other field is
optional. The `IntakeValidator` then decides whether each missing
field is `critical`, `warning` or `info`. This separation matters
because the same shape supports two different reviewer modes:

- A pre-flight check: "what's missing?" (validator's report).
- A real run: "produce a brief" (normalizer call).

### D-13.4 — Three severity levels (info / warning / critical)

The user spec asked for "missing", "warning if critical info is
missing". I split this into three buckets:

- `critical` — without this we cannot produce a brief at all
  (`product_or_service`, `commercial_objective`,
  `audience_description`, or an underivable slug).
- `warning` — we can produce a brief but the downstream output is
  noticeably worse (no industry, no budget, no competitors, etc.).
- `info` — the field is nice to have but downstream output is fine
  with a documented default or its absence.

This matches the three states a reviewer typically wants to see
(red / yellow / blue) and pairs with the existing
`{blocker, must, should}` checklist vocabulary.

### D-13.5 — The intake **NEVER** invents data

Missing fields stay empty. The only exception is **three operational
defaults** (`duration_weeks=8`, `primary_kpi=qualified_leads`,
`locale=es-AR`) that the pipeline already uses today. Each applied
default is recorded in
`IntakeValidationResult.operational_defaults_applied` and surfaced in
the Markdown summary so the reviewer can see what was filled.

Adding a fourth default would require a code change here AND in the
documentation; it's a deliberate friction.

### D-13.6 — Slug derivation is deterministic

`derive_slug(name)`: lowercase, non-alphanumeric runs collapsed to a
single dash, leading / trailing dashes stripped, clamped to 64 chars.
Reserved slugs (`_shared`) are rejected. Explicit override via
`client_slug_override` is honored when provided.

The slug is the only field the validator may **synthesize** (from
`client_name`); everything else is a pure pass-through or `None`.

### D-13.7 — The intake does NOT run the pipeline

`mkt intake` produces `outputs/<slug>/brief.json` and stops. The user
runs `mkt run-strategy` afterwards. Two reasons:

- The intake should be cheap and idempotent. A reviewer can re-run it
  ten times while iterating on the JSON without spawning a full
  strategy run each time.
- Auto-chaining would hide warnings: the strategy would just succeed,
  and the reviewer might miss that the budget was not provided.

### D-13.8 — The produced brief is 100% compatible with MKT-3A's `StrategyInputBrief`

The normalizer outputs an instance of `core.strategy.StrategyInputBrief`
(not a new type). Tests verify the round-trip:
`brief.to_json()` → `StrategyInputBrief.model_validate(...)` is
idempotent and `mkt run-strategy --brief <path>` accepts it as-is.

This means the intake layer is additive — existing users can keep
writing `brief.json` files directly if they want.

### D-13.9 — Audit events wrapped in `note` with action discriminator

Payload key `intake.action ∈ {created}`. Same wrapping pattern as
MKT-3B/3C/3D. A future `audit-trail.v2` will promote all four families
to first-class types in one motion.

### D-13.10 — Unknown channels surface as warning, then are dropped from the brief

The validator emits a `warning`-level entry per unknown channel value.
The normalizer silently drops them when producing the brief.

Two-stage handling avoids two bad outcomes:
- Hard-rejecting at the model layer would lose the entire intake on a
  typo.
- Silently dropping without surfacing would hide misconfigurations.

### D-13.11 — `--strict` CLI flag for CI

Without `--strict`, the CLI exits 0 even with critical issues (the
Markdown summary is still written so the reviewer can fix them).

With `--strict`, the CLI exits 4 when critical issues exist. CI
pipelines can use `--strict` to fail-fast on incomplete intakes.

The flag does NOT change disk side effects — they are written either
way.

### D-13.12 — Two memory kinds, both singleton `"current"`

- `client_intake` — what the human sent.
- `intake_validation` — what the validator decided.

Persisting both lets future tools (a portal, a diff view) compare
what was sent vs. what was flagged without recomputing.

Same singleton-id convention as the other packs (MKT-3A through 3D).
Versioned history is future work.

### D-13.13 — Outputs go to `outputs/<slug>/` (per-client subdirectory)

Earlier blocks wrote `outputs/*.md` directly. Intake introduces
per-client subdirectories so multiple intakes coexist without
overwriting each other. Future blocks should follow the per-slug
convention; the existing single-file outputs are still gitignored.

## Alternatives considered

- **Make `ClientIntake` strict** with every important field required.
  Rejected — the whole point is to accept incomplete intakes so the
  validator can report what's missing.
- **Hard-code more defaults** (e.g. infer `market` from `locale`).
  Rejected — defeats the no-fabrication invariant.
- **Auto-chain intake → run-strategy**. Rejected — D-13.7.
- **Single `intake_pack` memory kind** holding both the intake and
  the validation. Rejected — two kinds keeps them queryable
  separately and matches the per-pack pattern in 3A–3D.
- **Skip the Markdown summary and only write JSON**. Rejected — the
  summary is what makes the missing-fields list legible. A reviewer
  scanning JSON would miss it.
- **Hard-fail on unknown channels**. Rejected — D-13.10.

## Consequences

- An agency operator can hand a JSON file (or a form output) to the
  system and get a brief plus a Markdown report in one command.
- CI pipelines can use `--strict` to enforce intake completeness.
- The pipeline is now end-to-end reproducible from human input to
  visual direction without manual JSON authoring.
- The `outputs/<slug>/` convention sets the pattern for future
  per-client artifacts.
- A future web form / Notion import lands as a new front-end that
  produces the same `ClientIntake` shape; the rest of the pipeline
  needs no changes.

## Out of scope for MKT-3E

- Web form / landing page (explicitly out per user spec).
- Dashboard (explicitly out).
- Interactive `mkt intake --wizard` CLI mode.
- LLM-assisted intake completion.
- Multi-language intake (the demo mixes Spanish and English freely).
- Import adapters (Notion, Google Forms, Typeform).
- Intake-side image attachments (logos, reference visuals).
- Versioned intake history.
- `mkt intake diff` between two intake files.
