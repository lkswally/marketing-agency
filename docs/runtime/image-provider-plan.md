# Image Provider Selection & Generation Dry Run (MKT-7B)

Runtime guide for `mkt image-provider-plan`. Pure analysis +
dry-run preview layer on top of MKT-7A. Scores every candidate
provider against weighted criteria, picks one per job, emits a
per-job **dry-run receipt** — the simulated request shape a
future provider-integration block would send.

## Quick start

```bash
# Pre-req: a persisted ImageGenerationJobPack
mkt run-campaign --intake examples/intake/demo-business.json
mkt image-jobs --client <slug>

mkt image-provider-plan --client <slug>
```

Outputs land in `outputs/<slug>/image-provider-plan.{md,json}`
and the pack is persisted under
`<root>/<client>/image_provider_recommendation_pack/current.json`.

## What this block does NOT do

- Does NOT call any provider (OpenAI / Replicate / Stability /
  Canva / Figma / Midjourney).
- Does NOT generate any image.
- Does NOT import any SDK (`openai`, `replicate`, `stability_sdk`,
  `PIL`, `Pillow`).
- Does NOT read any credential — env vars are documented in the
  evaluation table by **name only**.
- Does NOT make HTTP calls. No `requests`, `httpx`, `urllib`,
  `aiohttp`.
- Does NOT write PNG / JPG / WebP / SVG.

Pinned by `test_no_provider_sdk_imported_anywhere`,
`test_no_http_lib_in_provider_plan_module`,
`test_no_credential_read_in_source`.

## Providers evaluated

| Provider          | Default model hint                  | Credentials required (NAMES ONLY) |
|-------------------|--------------------------------------|------------------------------------|
| `openai_images`   | `dall-e-3`                          | `OPENAI_API_KEY`                  |
| `replicate`       | `black-forest-labs/flux-schnell`    | `REPLICATE_API_TOKEN`             |
| `stability_ai`    | `stable-image-ultra`                | `STABILITY_API_KEY`               |
| `midjourney`      | `midjourney-v7`                     | `MIDJOURNEY_TOKEN` (broker)       |
| `canva`           | `canva-templates-v1`                | `CANVA_API_TOKEN`                 |
| `figma`           | `figma-export`                      | `FIGMA_API_TOKEN`                 |
| `manual`          | `agency-designer`                   | —                                  |

## Criteria scored (0..5 per provider)

The user-supplied list:

- `expected_quality`
- `cost`
- `api_support`
- `format_aspect_support`
- `integration_ease`
- `security`
- `style_control`
- `artifact_risk`
- `commercial_use`
- `external_dependency`

Per-piece-type weight overlays push the scoring towards what
matters for that piece. For example `landing_hero` weighs
`expected_quality` higher; `instagram_*` weighs `cost` and
`format_aspect_support` higher.

When no provider scores above the fallback floor (`12.0`) or
when the recommended pick is `manual`, the dry-run receipt is
marked `skipped_manual`.

## Outputs per job

For every job in the source `ImageGenerationJobPack`, the planner
emits:

### `ImageProviderRecommendation`
- `recommended_provider` + `recommended_score`
- `alternative_providers` (top 3 alternatives, excluding the pick)
- `fallback_provider` (always `manual`)
- `estimated_cost_usd`
- `rationale` (templated, deterministic)
- `risk_notes` (list — artifact risk / commercial use posture /
  external dependency / in-image text warning)

### `ProviderDryRunReceipt`
- `status` — one of `dry_run`, `skipped_blocked`, `skipped_manual`
- `model_hint`, `aspect_ratio`, `dimensions_px`,
  `prompt_length_chars`
- `simulated_output_filename` (TEXT suggestion — same value the
  MKT-7A factory wrote; no file exists on disk)
- `reason` (set when skipped)
- `notes`

`dry_run` is the only "would-have-called" status in this version
of the contract. A future provider-integration block will add
real-call statuses with a new contract version.

## Behaviour matrix

| Job state               | Receipt status         | Notes                                          |
|--------------------------|-------------------------|-------------------------------------------------|
| `draft` / `needs_review` / `ready_for_generation` + non-manual pick | `dry_run` | Request shape recorded; nothing sent. |
| Any state + recommended `manual` | `skipped_manual` | Designer composes manually. |
| `blocked` | `skipped_blocked` | Upstream block must be resolved first. |

## Pack-level stats

`ImageProviderRecommendationStats` carries:

- `total_jobs`
- `by_recommended_provider` (counts)
- `by_dry_run_status` (counts)
- `overrode_job_suggestion` — jobs where the planner picked a
  different provider than the MKT-7A factory's hint
- `skipped_blocked`, `skipped_manual`
- `total_estimated_cost_usd`

## Cardinal guarantees (test-pinned)

- No HTTP, no SDK, no `os.environ` / `os.getenv` anywhere in
  `core/image_provider_plan/`.
- No credential field on persisted models.
- Read-only over the source job pack (round-trip pinned).
- Deterministic — same inputs → same recommendations + receipts.
- Dry-run statuses are the only ones emitted (v1 contract).

## Exit codes

- `0` on success.
- `2` when no `ImageGenerationJobPack` exists for the client.

## NOT in scope (deferred — see PENDING.md)

- P-7B.1 — Per-tenant override of provider profiles.
- P-7B.2 — Per-job cost adjusted for dimensions + variants count.
- P-7B.3 — Live provider availability check (would require HTTP).
- P-7B.4 — Per-tenant override of the weight overlays.
- P-7B.5 — Real integration with `generated` status (separate
  block — MKT-7C — opt-in).
- P-7B.6 — Native `image_provider_recommendation_pack.v1` audit
  envelope.
- P-7B.7 — Cross-pack diff vs the previous plan ("OpenAI dropped
  in quality after pricing change — recompute").
