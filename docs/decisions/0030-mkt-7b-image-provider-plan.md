# ADR 0030 — MKT-7B: Image Provider Selection & Generation Dry Run

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-7B
- **Supersedes:** —
- **Contract:** `image-provider-recommendation-pack.v1` (new,
  Pydantic, in `core/image_provider_plan/models.py`).

## Context

MKT-7A ships the `ImageGenerationJobPack` with one job per
prompt variant plus a deterministic provider hint per piece
type. The next operational ask: a structured comparison of every
candidate provider against weighted criteria, with a concrete
recommendation per job and a dry-run preview of the request the
operator would eventually send.

Hard constraints the user repeated five times: no API call, no
SDK install, no credential read, no HTTP, no actual image
generation. Pure analysis + dry-run.

## Decision

### D-30.1 — Separate module `core/image_provider_plan/`

Parallel to `core/image_jobs/`. Same conventions: Pydantic
models with `extra="forbid"`, deterministic planner class,
dedicated renderer, CLI subcommand.

Rejected: extend MKT-7A's factory with a provider-comparison
sub-pack. That would couple two concerns (job materialisation
vs provider scoring) and force re-running MKT-7A whenever the
scoring rules evolved. Keeping them split lets the operator
re-score without rebuilding jobs.

### D-30.2 — Seven providers, ten criteria — module constants

`profiles.py` defines static frozen dataclasses for
`openai_images`, `replicate`, `stability_ai`, `midjourney`,
`canva`, `figma`, `manual`. Each carries:

- per-criterion score (0..5) for the ten user-listed criteria
- `estimated_cost_usd_per_image`
- `commercial_use_ok`
- `credentials_required` (NAMES of env vars only; values are
  never read)
- `supported_aspect_ratios`, `supported_formats`
- `integration_difficulty` / `external_dependency_risk` strings
- `model_hint`, `notes`

Per-tenant overrides are P-7B.1 / P-7B.4.

### D-30.3 — Weighted score with per-piece overlays

`_BASE_WEIGHTS` applies to every piece type. Per-piece
`_PIECE_TYPE_WEIGHT_OVERLAYS` add bumps that bias the score
towards what matters for that piece (hero pieces → quality; ads
→ style + low artifact; social → cost + format flexibility).

When the highest score falls below `_FALLBACK_SCORE_FLOOR` =
`12.0`, the planner falls back to `manual` — the always-safe
choice.

### D-30.4 — Aspect-ratio gate

Providers whose `supported_aspect_ratios` does not include the
job's aspect ratio (and is not `any`) are excluded from scoring
for that job. This prevents recommending a provider that
physically can't produce the requested format.

### D-30.5 — Three dry-run statuses, no real-call status in v1

`ProviderDryRunStatus` enum:

- `dry_run` — would have called provider X; request shape
  recorded.
- `skipped_blocked` — job is BLOCKED upstream; nothing recorded
  beyond the reason.
- `skipped_manual` — recommended path is `manual`; no provider
  request.

`v1` of the contract NEVER emits a real-call status. A future
MKT-7C block adds them with a new contract version. Pinned by
`test_planner_dry_run_status_is_only_dry_run_or_skipped`.

### D-30.6 — Receipt shape — never URL / credential

`ProviderDryRunReceipt` carries:

- `model_hint`, `prompt_length_chars`, `aspect_ratio`,
  `dimensions_px`, `simulated_output_filename`
- `reason` / `notes`

The receipt has NO `url`, NO `token`, NO `api_key`, NO
`customer_id`. Pinned by `test_no_credential_fields_on_receipt`.

### D-30.7 — Cost estimate is a static per-provider average

`estimated_cost_usd_per_image` × 1 image per recommendation.
Per-job adjustment for dimensions / variants count is P-7B.2 —
intentionally deferred to keep this block simple.

### D-30.8 — Provider profiles include `credentials_required`
as NAMES only

Env-var names appear on the evaluation table for the operator's
reference. The planner NEVER reads them. Pinned by
`test_no_credential_read_in_source` (grep for `os.environ` /
`os.getenv` in source).

### D-30.9 — Read-only over upstream packs

The planner reads the MKT-7A job pack and (best-effort) the
visual / creative / approval packs for cross-ref ids. It never
mutates any of them. Pinned by
`test_planner_does_not_mutate_job_pack`.

### D-30.10 — Audit envelope

Wrapped in `note` payload with key
`image_provider_recommendation_pack` carrying counts +
`total_estimated_cost_usd`. Native envelope tracked as P-7B.6.

### D-30.11 — CLI subcommand `mkt image-provider-plan`

`--client` required. Exit 0 on success, exit 2 when no
`ImageGenerationJobPack` exists. Same convention as every other
planner CLI.

### D-30.12 — Hard guarantees

- No HTTP, no SDK, no credential read, no image generation, no
  file write of binaries.
- All pinned by source-grep tests.

## Consequences

### Positive

- The operator gets a concrete, scored comparison of every
  candidate provider with per-job recommendations + dry-run
  receipts — without any provider integration shipping.
- The receipt's request shape lets the future MKT-7C block hit
  the ground running: same payload shape, fill in the URL +
  credential, send.
- Static profiles + weights are easy to evolve as providers
  change pricing / quality / availability.
- Per-job aspect-ratio gating prevents recommending a provider
  that can't produce the format.

### Negative / accepted trade-offs

- Per-tenant overrides absent (P-7B.1 / P-7B.4).
- Cost estimate is per-image average, not per-dimensions × variants
  (P-7B.2).
- No live availability check (P-7B.3) — would require HTTP,
  forbidden in this block.
- Audit envelope still wrapped in `note` (P-7B.6).
- Profile scores encode one author's intuition; per-tenant feedback
  loops are deferred.

## Out of scope (explicit)

- Any provider API call.
- Any SDK import.
- Any credential read.
- Any HTTP / scraping / MCP / n8n.
- Any image file write (PNG/JPG/WebP/SVG).
- The actual integration block — separate `MKT-7C` (opt-in,
  feature-flagged, idempotent).

## Validation

- 37 new tests across `tests/image_provider_plan/*` +
  `tests/cli/test_cli_image_provider_plan.py`:
  - 13 model tests
  - 13 planner + safety tests
  - 6 renderer tests
  - 5 CLI tests
- Full suite: green (1561 expected).
- Ruff: clean.
- ATLAS core: untouched.

## Related

- Depends on MKT-7A (`ImageGenerationJobPack`) and the upstream
  visual / creative / approval packs.
- Sets up future MKT-7C real-integration block (P-7B.5).
- Future work tracked as `P-7B.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/image-provider-plan.md`.
