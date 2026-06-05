# ADR 0031 — MKT-8A: Alpha Pilot Readiness + ATLAS Bridge Contract

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-8A
- **Supersedes:** —
- **Contracts shipped:**
  - `atlas-handoff-brief.v1` — envelope (`AtlasHandoffBrief`)
  - `landing-brief.v1` — `LandingBrief`
  - `branding-brief.v1` — `BrandingBrief`
  - `page-design-brief.v1` — `PageDesignBrief`

## Context

MARKETING-AGENCY-OS reached operational maturity at the end of
MKT-7B: strategy + creative + visual + approval + execution +
analytics + ads loop + image-job pack + image-provider plan all
work end-to-end without external side effects. The next step
was to:

1. Make the system safe to run against a real client for the
   first time (Alpha Pilot).
2. Define how MARKETING-AGENCY-OS will hand work over to the
   sibling ATLAS project for landing pages, branding and page
   design — **without** mixing repos, without reaching into
   ATLAS, and without any new external action.

MKT-8A is a docs-heavy block: it ships the ATLAS bridge contract
in code (so a future ATLAS integration cannot diverge silently)
plus a complete operator playbook.

## Decision

### D-31.1 — New module `core/atlas_bridge/`

`models.py` defines four Pydantic contracts:

- `LandingBrief` (`landing-brief.v1`)
- `BrandingBrief` (`branding-brief.v1`)
- `PageDesignBrief` (`page-design-brief.v1`)
- `AtlasHandoffBrief` (`atlas-handoff-brief.v1`) — envelope
  enforcing exactly one of the three populated, with kind
  matching.

`factory.py` builds a handoff from the persisted strategy +
optional approval / creative / visual / image-job packs.
`renderer.py` renders the handoff to Markdown.

### D-31.2 — Envelope enforces "exactly one"

`AtlasHandoffBrief.kind` and the three optional brief fields are
cross-checked by a `model_validator(mode="after")`:

- Exactly one of `landing_brief` / `branding_brief` /
  `page_design_brief` must be set.
- The populated one must match `kind`.

Pinned by `test_handoff_rejects_zero_briefs`,
`test_handoff_rejects_multiple_briefs`,
`test_handoff_rejects_kind_mismatch`.

### D-31.3 — Field name `body_copy`, not `copy`

`LandingSection.body_copy` and `PageDesignBlock.body_copy` are
deliberately named `body_copy` rather than `copy` because
`copy` shadows `pydantic.BaseModel.copy`. Pydantic emits a
warning when a field shadows an inherited method; we picked a
non-shadowing name. Pinned by
`test_landing_section_body_copy_does_not_shadow_copy_method`.

### D-31.4 — Persisted text only — no binary, no URL-only fields

`HandoffAssetReference` carries `asset_id`, `asset_kind`,
`label`, `filename_hint`, `notes`. There is NO field for inline
binary data, NO field for a real provider URL, NO field for a
credential.

`reference_links` (optional list of strings on the briefs) exists
so the operator can paste *inspiration* URLs ATLAS may inspect;
the handoff factory itself never fetches them.

### D-31.5 — CLI `mkt atlas-brief --client <slug> --kind <K>`

`--kind` is one of `landing` / `branding` / `page_design`.
`--page-name` only meaningful when `--kind page_design` (default
`about`). Exit 0 on success, exit 2 when there is no
`CampaignStrategyReport` or `--kind` is invalid.

Output filenames follow the spec:

- `outputs/<slug>/atlas-landing-brief.{md,json}`
- `outputs/<slug>/atlas-branding-brief.{md,json}`
- `outputs/<slug>/atlas-page-design-brief.{md,json}`

Persisted under `<root>/<client>/atlas_handoff_brief/current.json`.

### D-31.6 — Read-only over upstream packs

The factory loads strategy (required), approval / creative /
visual / image-job (optional). It mutates none of them. Pinned
by `test_factory_does_not_mutate_upstream_packs`.

### D-31.7 — `blocks_publish` mirrors upstream posture

`AtlasHandoffBrief.blocks_publish` is set to
`approval.blocks_publish or visual.blocks_publish`. The
Markdown renderer surfaces a WARNING banner so ATLAS knows
the campaign is on hold. Pinned by
`test_factory_blocks_publish_reflects_upstream` and
`test_render_landing_handoff_with_warning`.

### D-31.8 — No reach-in into ATLAS

`core/atlas_bridge/` imports nothing from `atlas`, references no
`ATLAS_API_URL`, no `atlas_core`, no `atlas.dispatcher`,
no `from atlas`. Pinned by `test_no_atlas_reach_in_anywhere`.

### D-31.9 — No HTTP, no SDK, no credential read

Same posture as the analytics / ads / image blocks. Pinned by
`test_no_http_lib_in_atlas_bridge_module` and
`test_no_credential_read_in_source`.

### D-31.10 — Real-business intake template ships separately

`examples/intake/alpha-pilot-template.json` carries:

- All standard intake fields with `<PLACEHOLDER>` markers.
- An `_alpha_pilot_notes` block with operator-only flags
  (`real_publication_authorised`, `real_image_generation_authorised`,
  `real_google_ads_writes_authorised`) — all default `false`
  with a `_safety_reminder` string.

The template is documented in
`docs/real-business-intake-template.md`.

### D-31.11 — Playbook + Definition of Ready + Definition of Done

Four operator docs ship under `docs/`:

- `alpha-pilot-playbook.md` — step-by-step pilot procedure.
- `alpha-pilot-checklist.md` — CLI inventory + recommended order.
- `alpha-pilot-definition-of-ready.md` — pre-pilot gate.
- `alpha-pilot-definition-of-done.md` — post-pilot gate.

Plus a runtime doc at `docs/runtime/atlas-bridge-handoff.md` for
the CLI itself.

### D-31.12 — Examples are real CLI outputs, not hand-written

`examples/atlas-bridge/landing-handoff-example.{md,json}`,
`…/branding-handoff-example.{md,json}`,
`…/page-design-handoff-example.{md,json}` are verbatim outputs
captured from `mkt atlas-brief` on the demo intake.
`examples/atlas-bridge/README.md` documents how to regenerate.

This is deliberate: hand-written examples drift from what the
factory actually emits. Regenerating after a contract change is
one CLI run away.

### D-31.13 — Audit envelope wrapped in `note`

Same trade-off as every previous block. Native
`atlas_handoff_brief.v1` envelope deferred (P-8A.7).

### D-31.14 — Contract versioning policy

- `v1` is the only version of each contract. Breaking changes
  ship as `v2` with a new contract file — never silently
  mutating `v1`.
- Adding optional fields to `v1` is allowed and does not break
  ATLAS consumers as long as `extra="forbid"` is preserved.
- Removing or renaming fields requires `v2`.

## Consequences

### Positive

- The operator can run a controlled real-client pilot end-to-end
  with a documented procedure, a pre-flight gate, a post-flight
  gate, and a complete CLI inventory.
- ATLAS gets a structured contract it can validate against —
  unknown fields are rejected by `extra="forbid"`.
- Examples drift-proof: a contract change forces an example
  regeneration, not a doc edit.
- Zero risk of MARKETING-AGENCY-OS reaching into ATLAS — the
  module imports nothing from ATLAS and is grep-pinned.
- The pilot is safe to run today against a real business
  because every potentially-mutating action stays disabled at
  the source.

### Negative / accepted trade-offs

- The intake template's safety flags are advisory. A future
  block could add a `mkt intake --strict-alpha-pilot` mode that
  validates all flags are `false` before any pipeline step.
- The bridge factory's text helpers (`_audience_text`,
  `_value_prop_text`, etc.) are defensive — they probe the
  strategy schema via `model_dump` rather than typed attribute
  access — so they continue to work if the strategy schema
  evolves. Trade-off: weaker static typing inside the bridge.
- Audit envelope still wrapped in `note`.
- The handoff factory currently provides one auto-generated
  landing section list (`hero` → `value_proposition` → `proof`
  → `cta`). Per-tenant overrides are P-8A.2.

## Out of scope (explicit)

- Any real ATLAS API call.
- Any real landing-page generation.
- Any real publication / Vercel deploy.
- Any real n8n / MCP integration.
- Any real image generation.
- Any real email send.
- Validating ATLAS's response after the operator hands the
  brief over (operator captures it in their own log).

## Validation

- 36 new tests (`tests/atlas_bridge/*` + `tests/cli/test_cli_atlas_handoff.py`).
- Full suite (after the rename to `mkt atlas-brief`): green.
- Ruff: clean.
- ATLAS core: untouched.
- Examples regenerated from a fresh pipeline run on the demo
  intake — three brief pairs in `examples/atlas-bridge/`.

## Related

- Builds on every block from MKT-1 through MKT-7B (strategy,
  creative, visual, approval, execution, analytics, ads, image
  jobs, image provider plan).
- Sets up future MKT-8B / MKT-9A blocks that will integrate the
  ATLAS read-back loop and the real-publication / portal MVP.
- Future work tracked as `P-8A.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/atlas-bridge-handoff.md`.
- Playbook: `docs/alpha-pilot-playbook.md`.
