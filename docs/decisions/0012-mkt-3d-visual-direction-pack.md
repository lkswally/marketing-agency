# ADR 0012 — MKT-3D: Visual Direction & Image Prompt Pack

- **Status:** Accepted
- **Date:** 2026-05-30
- **Block:** MKT-3D
- **Supersedes:** —
- **Contracts:** `visual-direction-pack.v1` (new, Pydantic, in
  `core/visual/models.py`).

## Context

MKT-3A delivered a strategic deliverable (the report). MKT-3B added
the compliance audit (Approval Pack with `blocks_publish`). MKT-3C
shipped the operational copy layer (Creative Asset Pack with A/B
variants per asset and a per-piece calendar).

What was still missing was the **visual layer**: per-channel piece
specifications, structured prompts with all 12 fields a designer
needs, a campaign-wide style guide, visual risks to avoid.

MKT-3D fills that. Like the prior blocks, it is deterministic,
LLM-free, no external API, no image generation, never publishes.

## Decision

### D-12.1 — Deterministic templates, no LLM, no image generation

Same posture as MKT-3A / MKT-3B / MKT-3C. The factory composes
visual directions from declared specs (`DEFAULT_PIECE_SPECS`) and
variant generators (`_variant_a_editorial`, `_variant_b_bold`).

Promotion to LLM-backed generation requires the safety boundaries in
`docs/runtime/agent-backend-safety.md`. The block ships the data
model and the operational pipeline; the next generator swaps in
without touching the model.

### D-12.2 — `core/visual/` is its own package

Alongside `core/strategy/`, `core/approval/`, `core/creative/`. The
visual direction is narrower than the creative pack (only visual
specs) but deserves its own package because it can later receive
real image-generation adapters without contaminating the operational
copy layer.

Strategy → approval → creative → visual is the canonical flow.

### D-12.3 — Always 11 piece types regardless of channel mix

The factory produces a `PieceVisualDirection` for every
`PieceType`, not only the channels the strategy recommends. Why?

- Predictability for the designer: she always reads the same 11
  sections in the Markdown rendering.
- Some piece types (`flyer_square`, `flyer_vertical`, `landing_hero`)
  are channel-agnostic and useful regardless of the recommended mix.
- A piece type that ends up unused is left in `DRAFT` state and
  costs nothing.

Adding a 12th piece type later is additive (catalogue entry +
documentation update); it does not change the contract.

### D-12.4 — State derivation reuses MKT-3C policy

The function `_derive_state_for_directions` is logically identical
to MKT-3C's `_derive_state_for_assets`:

| Condition | State |
|-----------|-------|
| `blocks_publish=True` | `BLOCKED` |
| `APPROVED` AND not blocking | `READY_FOR_PUBLISH` |
| Severity risky/unsafe AND not approved | `BLOCKED` (via blocks_publish) |
| Caveat-only or safe AND not approved | `DRAFT` |
| No Approval Pack | `NEEDS_REVIEW` |

There is no asset-level override — same justification as MKT-3C
D-11.4.

### D-12.5 — Campaign-wide style guide (single instance per pack)

`style_guide` is one object on the pack, not one per piece. Rationale:
visual identity is campaign-level. Differentiating per piece would
fragment the brand across the same campaign.

The 11 piece-type directions consume the same style guide and
contribute to a coherent visual whole.

### D-12.6 — Two prompt variants per piece (A: editorial, B: bold)

Same count and labels as MKT-3C variants. Two is the minimum useful
for A/B testing. Three would multiply combinations without
proportional analytical benefit at this stage.

The two angles (editorial photography vs bold typographic poster)
cover the dominant design choices most campaigns face.

### D-12.7 — `negative_prompt` is per piece type + reinforced per variant

The `PieceTypeSpec.typical_negative_prompt` is the per-channel
baseline (e.g. Instagram Story negatives: cropped faces near edges).
Each variant's `negative_prompt` field can carry further constraints.

This separation matters because an Instagram Story and an Email
Header have very different failure modes; one universal negative
prompt would be both too noisy and too narrow.

### D-12.8 — Visual risks are campaign-global, not per piece

Per-piece risks would balloon the pack with repetition. The
campaign-level `global_visual_risks` list captures the universal
failure modes (stock cliché, off-brand palette, accessibility, AI
artifacts, IP violation).

Per-piece sensitivity is captured by the per-piece checklist.

### D-12.9 — Optional reference to source creative artifacts

When a Creative Asset Pack is supplied, the factory matches piece
types to creative asset ids and image-prompt ids when possible:

- A `flyer_square` direction references the matching `FlyerAsset` from
  MKT-3C (and inherits its `scheduled_for`).
- The `instagram_carousel` direction references the carousel image
  prompt when the brief produced one.

These are optional references; missing matches do not break the
build.

### D-12.10 — Audit events wrapped in `note` with action discriminator

Payload key `visual_pack.action ∈ {created, updated}`. Same pattern
as MKT-3B and MKT-3C. A future `audit-trail.v2` bump will promote
`approval_pack_*`, `creative_pack_*` and `visual_pack_*` to
first-class event types in one motion.

### D-12.11 — `scheduled_for` backfilled from the Creative Pack when matched

When a creative asset's `scheduled_for` is known and its piece type
matches an MKT-3D direction, the direction inherits the date. This
way the calendar discipline of MKT-3C surfaces inside the visual
pack without duplicating scheduling logic.

Unmatched directions get `scheduled_for=None`; this is intentional
(image prompts are reusable, not date-bound).

### D-12.12 — NO image generation. EVER (in this block).

The pack is 100% text. No PNG, no JPG, no WebP, no MP4. No call to
any image API. The dependency tree of `core/visual/` contains no
image-generation SDK.

A future image-generation block will land as a separate adapter
consuming this pack as input. The pack's data model will not change.

### D-12.13 — Reuse `CreativeAssetState` instead of a new enum

Visual directions live in the same state machine as creative assets:
`DRAFT` / `NEEDS_REVIEW` / `READY_FOR_PUBLISH` / `BLOCKED`. The
`PUBLISHED` value still does not exist in the codebase (ADR 0011
D-11.12).

Reusing the enum keeps consumers from learning a second vocabulary
that happens to mean the same thing.

### D-12.14 — `mkt build-visuals --require-approval` exits 3 when blocked

Same flag and exit-code convention as `mkt build-creatives`. Ops
scripts can chain:

```bash
mkt run-strategy --audit && \
mkt build-creatives --client demo-saas --require-approval && \
mkt build-visuals    --client demo-saas --require-approval
```

with a single failure mode (exit 3) anywhere along the chain.

## Alternatives considered

- **LLM-backed prompt generation now.** Rejected — D-12.1.
- **Conditional piece type generation based on channel mix.** Rejected
  (D-12.3) — predictability beats minimalism for the designer.
- **Per-piece style guide.** Rejected (D-12.5) — fragments brand.
- **Three or four variants per piece.** Rejected (D-12.6) — same
  reasoning as MKT-3C D-11.5.
- **New `VisualState` enum separate from `CreativeAssetState`.**
  Rejected (D-12.13) — duplication without value.
- **Add `PUBLISHED` to the state enum** to mark images as shipped.
  Rejected (same as MKT-3C D-11.12) — publication is a runtime concept
  belonging to a separate log entity.
- **Render images alongside prompts** with a small wrapper around a
  stub image API. Rejected (D-12.12) — the moment an image API
  exists, the safety scope of this block changes entirely. Keeping it
  text-only preserves the safety posture.

## Consequences

- A designer can pick up `outputs/visual-direction-pack.md` and have
  everything she needs to brief an illustrator or paste prompts into
  any image generation tool.
- Future image-generation blocks consume the pack via
  `VisualPromptVariant.full_prompt_text` + `negative_prompt` without
  needing strategic context.
- The four-layer pipeline (strategy → approval → creative → visual)
  has a consistent state model and audit story. An operational
  pipeline can chain all four with a single failure mode.
- The "no image" guarantee is encoded in absence: no image SDK is
  imported anywhere in `core/visual/`.

## Out of scope for MKT-3D

- LLM-backed prompt generation (better contextualization of
  style/tone).
- Real image generation.
- More than two variants per piece type.
- Per-client custom visual style overrides loaded from disk.
- Import of `Brand.visual_rules` (MKT-1B) into the style guide
  automatically (the guide is template-driven for now).
- Figma frame export.
- Image-content audit (MKT-3B audits text only).
- A `mkt visual diff` / `preview` / `publish` CLI surface.
- Per-prompt outcome tracking (A vs B winner).
- Workflow-level integration with W7.
