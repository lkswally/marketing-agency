# Image Generation Job Pack (MKT-7A)

Runtime guide for `mkt image-jobs`. Deterministic translator
that turns a persisted `VisualDirectionPack` into a structured
set of **image-generation jobs the operator reviews before any
provider is ever invoked.**

## Quick start

```bash
# Pre-req: a VisualDirectionPack exists for the client (from the
# normal pipeline).
mkt run-campaign --intake examples/intake/demo-business.json

# Build the image jobs pack:
mkt image-jobs --client acme
```

Outputs land in `outputs/<slug>/image-generation-jobs.{md,json}`
and the pack is persisted under
`<root>/<client>/image_generation_job_pack/current.json`.

## What this block does NOT do

- Does NOT generate any image.
- Does NOT call OpenAI / Replicate / Midjourney / Stability /
  Canva / Figma — or any other provider.
- Does NOT write PNG / JPG / WebP / SVG files.
- Does NOT import any image SDK (Pillow, openai, replicate, …).

The pack is a **review-only deliverable**. A future block will
integrate one or more real providers behind a feature flag
(see P-7A.6 / future MKT-7B).

## Jobs

One `ImageGenerationJob` per `(PieceVisualDirection,
VisualPromptVariant)` pair in the visual pack. Each job carries:

| Field                          | Source / meaning |
|--------------------------------|------------------|
| `job_id`                       | Fresh uuid       |
| `piece_type`                   | `PieceVisualDirection.piece_type` (string) |
| `channel`                      | `PieceVisualDirection.channel` |
| `direction_id`, `variant_id`   | back-refs to the source visual rows |
| `creative_ref`                 | `source_creative_asset_id` if present |
| `image_prompt_ref`             | `source_creative_image_prompt_id` if present |
| `prompt`                       | `VisualPromptVariant.full_prompt_text` verbatim |
| `negative_prompt`              | `VisualPromptVariant.negative_prompt` verbatim |
| `aspect_ratio`                 | from variant |
| `dimensions_px`                | from `PieceTypeSpec` |
| `in_image_text`                | from variant |
| `visual_style`, `intended_use` | from variant |
| `output_filename_suggestion`   | `<slug>--<piece_type>--<variant_id>.png` |
| `provider_suggestion`          | deterministic heuristic — see below |
| `provider_rationale`           | one-liner explaining the heuristic choice |
| `state`                        | see state derivation below |
| `blocked_reason`               | populated when state is `BLOCKED` |
| `review_checklist`             | per-job reviewer items |

## Job states

| State                   | Meaning                                            |
|--------------------------|----------------------------------------------------|
| `draft`                  | Job needs editorial work before submission.        |
| `needs_review`           | Reviewer must sign off before submission.          |
| `blocked`                | Upstream approval / direction blocks the job.      |
| `ready_for_generation`   | Job is ready to hand to a provider integration.    |
| `generated`              | **RESERVED** — never emitted by MKT-7A factory.    |

### State derivation rules (in order)

1. `ApprovalPack.blocks_publish == True` → ALL jobs `BLOCKED`.
2. Source `PieceVisualDirection.state == BLOCKED` → job `BLOCKED`.
3. `VisualDirectionPack.blocks_publish == True` → job `BLOCKED`.
4. Source direction `state == NEEDS_REVIEW` → job `NEEDS_REVIEW`.
5. Source direction `state == READY_FOR_PUBLISH` → job
   `READY_FOR_GENERATION`.
6. Otherwise → `DRAFT`.

`generated` is reserved for the future provider-integration block.
The MKT-7A factory NEVER emits it. Pinned by
`test_factory_source_has_no_generated_emission` and
`test_factory_never_emits_generated`.

## Provider suggestion heuristic

| Piece type                                                  | Suggested provider |
|--------------------------------------------------------------|--------------------|
| `flyer_square`, `flyer_vertical`, `ad_creative`              | `midjourney`       |
| `email_header`, `landing_hero`                               | `openai_images`    |
| `instagram_*`, `reels_cover`                                 | `replicate`        |
| `linkedin_post_graphic`, `facebook_post`                     | `canva`            |
| anything else                                                | `manual`           |

These are **advisory only**. The operator decides whether to use
them when a real provider integration lands. The
`provider_suggestion` value does NOT trigger any side effect.

## Cardinal guarantees (test-pinned)

- **No image generation, no provider call.**
- **No image SDK imported** anywhere in `core/image_jobs/`
  (`test_no_provider_sdk_imported_anywhere`).
- **No HTTP library imported** in `core/image_jobs/`
  (`test_no_http_lib_in_image_jobs_module`).
- **`ImageJobState.GENERATED` is reserved** — factory source
  contains no assignment to it
  (`test_factory_source_has_no_generated_emission`).
- **Deterministic** — same visual pack → same job layout +
  provider suggestions (`test_factory_provider_suggestion_is_deterministic`).
- **Read-only** over the source pack — the factory never mutates
  it. The block writes one new artifact:
  `image_generation_job_pack/current.json`.

## Exit codes

- `0` on success.
- `2` when no `VisualDirectionPack` exists for the client.

## NOT in scope (deferred — see PENDING.md)

- P-7A.1 — Per-tenant override of the provider heuristic.
- P-7A.2 — Cost estimate per job (provider × dimensions).
- P-7A.3 — Reference image attachment (style transfer inputs).
- P-7A.4 — Multi-output jobs (one prompt → N renders).
- P-7A.5 — Job grouping by campaign / launch wave.
- P-7A.6 — Real provider integration with `generated` state +
  uploaded asset URI persistence (separate block, opt-in).
- P-7A.7 — Native `image_generation_job_pack.v1` audit envelope.
- P-7A.8 — Promotion of `ready_for_generation` jobs into the
  next `CampaignExecutionTaskPack`.
