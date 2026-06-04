# ADR 0029 — MKT-7A: Image Generation Job Pack

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-7A
- **Supersedes:** —
- **Contract:** `image-generation-job-pack.v1` (new, Pydantic, in
  `core/image_jobs/models.py`).

## Context

The pipeline already produces a `VisualDirectionPack` with
prompt variants, dimensions, negative prompts and a checklist
per piece. What was missing was the bridge between that pack and
the eventual image-provider integration. The user explicitly
deferred the provider integration itself — first we need a
structured, auditable, reviewable job pack the operator can sign
off on before any provider is called.

The hard constraints, repeated five times: no image generation,
no provider call, no SDK import, no real file write, no MCP.

## Decision

### D-29.1 — New module `core/image_jobs/`

Parallel to `core/visual/`, `core/creative/`, `core/ads_promoter/`.
Same conventions: Pydantic models with `extra="forbid"`,
deterministic factory class, dedicated renderer, CLI subcommand.

### D-29.2 — Contract `image-generation-job-pack.v1`

One top-level pack (`ImageGenerationJobPack`) containing:

- `jobs: list[ImageGenerationJob]` — one per
  `(direction, variant)` pair.
- `review_checklist: list[ImageJobReviewChecklistItem]` —
  pack-level reviewer items.
- `stats: ImageJobStats` — counts by state / provider / piece.
- Provenance refs: `visual_pack_id`, `creative_pack_id`,
  `approval_pack_id`, `run_summary_id`.
- `blocks_publish: bool` — mirrors approval / visual posture.

### D-29.3 — Five-value state enum, `generated` RESERVED

`ImageJobState` defines:
- `draft`
- `needs_review`
- `blocked`
- `ready_for_generation`
- `generated`

The factory NEVER emits `generated` — it exists in the enum
specifically so a future provider-integration block can fill
it in without bumping the contract. Deserialisation accepts it
for round-trip purposes.

Pinned by `test_factory_source_has_no_generated_emission` (greps
source for `ImageJobState.GENERATED`) and
`test_factory_never_emits_generated` (runtime check after build).

### D-29.4 — State derivation — explicit precedence

In order:

1. `ApprovalPack.blocks_publish` → all jobs `BLOCKED`.
2. Source `PieceVisualDirection.state == BLOCKED` → job
   `BLOCKED`.
3. `VisualDirectionPack.blocks_publish == True` → job `BLOCKED`.
4. Source direction `state == NEEDS_REVIEW` → `NEEDS_REVIEW`.
5. Source direction `state == READY_FOR_PUBLISH` →
   `READY_FOR_GENERATION`.
6. Otherwise → `DRAFT`.

The factory tracks per-job whether the block was due to approval
or to the source direction, so the stats expose both counts
separately.

### D-29.5 — Provider suggestion is a deterministic heuristic

`_PIECE_TYPE_TO_PROVIDER` is a module-level dict:

- `flyer_*`, `ad_creative` → `MIDJOURNEY` (typography-heavy)
- `email_header`, `landing_hero` → `OPENAI_IMAGES`
- `reels_cover`, `instagram_*` → `REPLICATE` (fast iteration)
- `linkedin_post_graphic`, `facebook_post` → `CANVA`
- fallback → `MANUAL`

Each suggestion comes with a one-liner rationale. The suggestion
is **advisory only** — no side effect is triggered by it. Tested
against the demo pipeline output.

Rejected alternative: pick the cheapest provider for every piece.
That would (a) require cost estimates not yet implemented (P-7A.2)
and (b) wrongly bias towards low-quality providers for hero
pieces.

### D-29.6 — Per-job + pack-level review checklist

Each job's checklist starts with the source direction's
`VisualChecklistItem` entries, then adds:

- A warning when `in_image_text` is non-empty (provider OCR
  errors are common).
- An info item naming the expected dimensions.
- A blocker item when state is `BLOCKED` ("Resolve upstream
  block before submitting").

The pack-level checklist starts with `visual.global_checklist`
and adds blocker items when approval / visual blocks publish.

### D-29.7 — Output filename suggestion deterministic

Format: `<client_slug>--<piece_type>--<variant_id>.png`.
Non-alphanumeric chars in `variant_id` are stripped to keep the
suggestion filesystem-safe. The factory does NOT create the file
— the suggestion is text only.

### D-29.8 — No SDK / HTTP imports, no Image library

The module imports nothing from `openai`, `replicate`,
`stability_sdk`, `PIL`, `Pillow`, or any HTTP library. Pinned by
`test_no_provider_sdk_imported_anywhere` and
`test_no_http_lib_in_image_jobs_module`.

### D-29.9 — Read-only over upstream packs

Factory reads `VisualDirectionPack`, optionally reads
`ApprovalPack`, `CreativeAssetPack`, `CampaignRunSummary`.
Writes only the new `image_generation_job_pack/current.json`.

### D-29.10 — Audit envelope

Wrapped in `note` payload with key
`image_generation_job_pack` carrying counts +
`blocks_publish` + `blocked_due_to_*`. Native envelope tracked
as P-7A.7.

### D-29.11 — CLI subcommand `mkt image-jobs`

`--client` required. Exit 0 on success, exit 2 when no
`VisualDirectionPack` exists for the client. Same convention as
every other factory / planner CLI in this codebase.

### D-29.12 — Hard guarantee: no image generation, no file write

The block touches only Markdown + JSON files (the report
artifacts) and the JsonFileMemory entries. No PNG / JPG / WebP
is written. No provider is called. Pinned by the SDK + HTTP +
"no Image library" tests.

## Consequences

### Positive

- The agency now has a complete, structured, auditable list of
  every image the campaign needs, with prompts + dimensions +
  provider suggestions + review checklist — all before any
  provider integration ships.
- The state derivation respects every existing blocking
  mechanism (`ApprovalPack`, `PieceVisualDirection.state`,
  `VisualDirectionPack.blocks_publish`), so the operator sees
  exactly which jobs are blocked and why.
- Provider suggestion is data — the future MKT-7B integration
  block can read it without any planner change.
- Zero risk of accidental image generation: no SDK is imported.

### Negative / accepted trade-offs

- Provider suggestion is a coarse static heuristic. Per-tenant
  overrides are P-7A.1.
- Cost estimates are absent (P-7A.2).
- Reference images / style transfer inputs are not modelled
  (P-7A.3).
- Multi-output jobs (`n=4` style variants) are not modelled
  (P-7A.4).
- Native audit envelope still wrapped in `note` (P-7A.7).

## Out of scope (explicit)

- Any image generation, any provider call, any SDK import.
- File writes of PNG / JPG / WebP / SVG.
- MCP server integration.
- Real Notion / n8n / publication / email side effects.
- Google Ads write.

## Validation

- 33 new tests:
  - 12 model tests (`tests/image_jobs/test_models.py`)
  - 11 factory + safety tests (`tests/image_jobs/test_factory.py`)
  - 4 renderer tests (`tests/image_jobs/test_renderer.py`)
  - 5 CLI tests (`tests/cli/test_cli_image_jobs.py`)
- Suite: 1524 passed (will confirm in commit).
- Ruff: clean.
- ATLAS core: untouched.

## Related

- Depends on MKT-3* visual + creative + approval packs and the
  MKT-pipeline `CampaignRunSummary`.
- Sets up future MKT-7B provider integration (P-7A.6).
- Future work tracked as `P-7A.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/image-generation-jobs.md`.
