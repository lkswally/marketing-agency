# Visual Direction & Image Prompt Pack (MKT-3D)

> Status: **implemented** (MKT-3D).
> Module: `core.visual`.
> Backend: deterministic templates (no LLM, no image API, no PNG/JPG produced).
> Contract: `visual-direction-pack.v1`.
> CLI entry: `mkt build-visuals --client <slug>`.

The Visual Direction Pack is the **visual layer** of the agency
pipeline. Where MKT-3A produces the strategy report, MKT-3B audits
claims, and MKT-3C assembles the per-asset creative pack, MKT-3D
prepares **everything a designer or image-generation tool needs** to
produce the visual assets — without ever generating a single pixel.

The pack is 100% text. No image is created. No image API is called.
The terminal positive state is `READY_FOR_PUBLISH`; `PUBLISHED` does
not exist in the codebase.

---

## 1. What it produces

- A **campaign-wide style guide** (palette, typography, mood,
  composition principles, do / do not).
- **11 piece-type directions** (Instagram post / story / carousel,
  LinkedIn post, Facebook post, Reels cover, email header, landing
  hero, ad creative, flyer square / vertical), each with its
  dimensions, aspect ratio, safe zones, text guidelines, delivery
  notes and typical negative prompt.
- **2 prompt variants per piece type** — Variant A (editorial),
  Variant B (bold typographic). Each variant carries the 12 user-spec
  fields (objective, audience, style, tone, composition, in-image
  text, elements, colors, aspect ratio, restrictions, negative prompt,
  intended use) plus a ready-to-paste `full_prompt_text`.
- **Global visual risks** (stock cliché, off-brand palette,
  accessibility, AI artifacts, IP violation).
- **Per-direction checklist** + **pack-wide global checklist**.
- **References** to upstream artifacts (`report_id`,
  `approval_pack_id`, `creative_pack_id`) and to specific creative
  assets when matched (`source_creative_asset_id`,
  `source_creative_image_prompt_id`).

The full pack is persisted to memory and rendered to both Markdown
(`outputs/visual-direction-pack.md`) and JSON
(`outputs/visual-direction-pack.json`).

---

## 2. State derivation

The pack's overall state — and each direction's state — is derived
from the Approval Pack (MKT-3B). The policy is identical to MKT-3C:

| Condition | State |
|-----------|-------|
| No Approval Pack persisted | `NEEDS_REVIEW` |
| `ApprovalPack.blocks_publish == True` | `BLOCKED` |
| `ApprovalPack.state == APPROVED` AND not blocking | `READY_FOR_PUBLISH` |
| Severity in {risky, unsafe} not approved | `BLOCKED` (via blocks_publish) |
| Caveat-only / safe, not approved | `DRAFT` |

There is no asset-level override. If the audit decided the campaign
blocks publication, every direction is blocked.

---

## 3. Architecture

```
CampaignStrategyReport (MKT-3A)
     +
ApprovalPack (MKT-3B, optional)
     +
CreativeAssetPack (MKT-3C, optional)
         │
         ▼
VisualPromptFactory.build(report, approval_pack, creative_pack)
         │
         │ deterministic templates
         │   + 11 piece-type specs
         │   + 2 prompt variants per piece
         │   + campaign-wide style guide
         │   + global visual risks
         │   + state derivation
         │   + creative asset → scheduled date backfill
         │
         ▼
VisualDirectionPack (state=derived)
         │
         ▼
VisualPromptFactory.persist(pack)
         │
         │ writes:
         │   data/clients/<slug>/visual_direction_pack/current.json
         │ emits audit event:
         │   {action: created|updated, ...}
         │
         ▼
Markdown + JSON written to outputs/
```

### 3.1 Module map (`core/visual/`)

| File | Purpose |
|------|---------|
| `models.py` | Pydantic: `VisualDirectionPack`, `PieceVisualDirection`, `VisualPromptVariant`, `VisualStyleGuide`, `VisualRisk`, `VisualChecklistItem`. |
| `specs.py` | `PieceType` enum (11 values) + `PieceTypeSpec` + `DEFAULT_PIECE_SPECS` catalogue. |
| `prompt_factory.py` | `VisualPromptFactory` + state derivation + variant generators + `build_and_persist`. |
| `renderer.py` | Pure Markdown renderer. |

### 3.2 Memory kind

- `visual_direction_pack` — singleton id `"current"` per client.

### 3.3 Audit events

Every `persist` emits `event_type=note` with
`payload.visual_pack.action ∈ {"created", "updated"}`. Same wrapping
pattern as MKT-3B and MKT-3C.

---

## 4. The 11 piece types

| Piece type | Aspect ratio | Dimensions | Channel |
|------------|--------------|------------|---------|
| `instagram_post` | 1:1 | 1080×1080 | Instagram |
| `instagram_story` | 9:16 | 1080×1920 | Instagram |
| `instagram_carousel` | 1:1 (per slide) | 1080×1080 (3–7 slides) | Instagram |
| `linkedin_post_graphic` | 1.91:1 | 1200×628 | LinkedIn |
| `facebook_post` | 1.91:1 | 1200×628 | Facebook |
| `reels_cover` | 9:16 | 1080×1920 | TikTok / IG Reels |
| `email_header` | 3:1 | 600×200 | Email |
| `landing_hero` | 16:9 | 1920×1080 | Landing |
| `ad_creative` | multiple | 1080×1080 / 1080×1920 / 1200×628 | Paid social |
| `flyer_square` | 1:1 | 1080×1080 | Print/share |
| `flyer_vertical` | 4:5 | 1080×1350 | Stories/print |

Each spec includes safe zones, text guidelines, file format hints,
delivery notes and a typical negative prompt.

---

## 5. The 12 fields per variant

Every `VisualPromptVariant` carries these 12 fields exactly:

1. `objective` — what the piece accomplishes.
2. `target_audience` — audience label.
3. `visual_style` — editorial / typographic / bold / etc.
4. `emotional_tone` — confident / curious / direct / etc.
5. `composition` — rule of thirds / typographic dominance / etc.
6. `in_image_text` — text overlay suggestions.
7. `visual_elements` — sujeto, iluminación, etc.
8. `suggested_colors` — hex palette.
9. `aspect_ratio` — canonical string.
10. `restrictions` — what to avoid for this variant.
11. `negative_prompt` — failure-mode terms.
12. `intended_use` — channel / placement label.

Plus a single `full_prompt_text` that assembles them into a
ready-to-paste string.

Both variants (A: editorial, B: bold typographic) are generated for
every piece type, regardless of channel mix. Predictability for the
designer beats conditional production.

---

## 6. CLI usage

```bash
# Prerequisite: strategy is persisted (audit + creative pack are optional).
mkt run-strategy --brief examples/clients/demo-saas/brief.json --audit
mkt build-creatives --client demo-saas   # optional but recommended

# Build the visual direction pack:
mkt build-visuals --client demo-saas
```

Exit codes:

- `0` — pack produced.
- `2` — no persisted `CampaignStrategyReport` for the client.
- `3` — `--require-approval` was set AND `ApprovalPack.blocks_publish == True`.

Output to stdout is a JSON summary. Disk side effects:

- `outputs/visual-direction-pack.md` — full Markdown rendering.
- `outputs/visual-direction-pack.json` — same content as JSON.
- `data/clients/<slug>/visual_direction_pack/current.json` — persisted
  Pydantic dump.
- An audit event recording the action.

---

## 7. Programmatic API

```python
from pathlib import Path

from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline
from core.approval import ApprovalPackBuilder
from core.creative import CreativeFactory
from core.visual import VisualPromptFactory, render_markdown_pack

mem = JsonFileMemory(Path("data/clients"))

report = StrategyPipeline(memory=mem).run_from_path(
    "examples/clients/demo-saas/brief.json"
).report

builder = ApprovalPackBuilder(memory=mem)
ap = builder.build_from_report(report)
builder.persist(ap)

cp = CreativeFactory(memory=mem).build(report, ap)

factory = VisualPromptFactory(memory=mem)
pack = factory.build(report, ap, cp)
factory.persist(pack)

print(render_markdown_pack(pack))
```

---

## 8. Layering

```
CampaignStrategyReport            (MKT-3A, strategic)
        │ feeds
        ▼
ApprovalPack                      (MKT-3B, compliance)
        │ derives state for
        ▼
CreativeAssetPack                 (MKT-3C, operational copy)
        │ provides asset IDs + schedule for
        ▼
VisualDirectionPack               (MKT-3D, visual direction)
        │ blocks_publish honored by
        ▼
Future image gen / publishers     (post-MCP, not implemented)
```

Each layer is a separate package. They share `core.contracts` /
`core.domain` / `core.memory` but do not import each other beyond
their immediate upstream.

---

## 9. The "no image generated" guarantee

The pack is text. The codebase ships:

- Zero call to any image API (Replicate / Midjourney / DALL-E /
  Imagen / Stable Diffusion / etc.).
- Zero PNG, JPG, WebP, MP4 or any other binary written.
- Zero import of any image-generation SDK.

This is policy AND fact: no relevant import sits in the dependency
tree. A future image-generation block will land as a separate adapter
(`integrations/image_*.py`) consuming this pack as input. The pack
itself will not change.

---

## 10. The "never published" guarantee

`CreativeAssetState` is reused from MKT-3C. It exposes four states:

```python
DRAFT
NEEDS_REVIEW
READY_FOR_PUBLISH
BLOCKED
```

There is no `PUBLISHED`. Tests in
`tests/visual/test_prompt_factory.py::test_no_direction_is_ever_published`
pin this property.

---

## 11. Limitations (and where they open)

| Concern | Block |
|---------|-------|
| LLM-backed prompt generation (richer, context-aware) | dedicated block, post-Claude Code safety |
| Real image generation from the prompts | post-MCP / Replicate / image gen block |
| 3+ prompt variants per piece type | continuation block |
| Per-client custom visual style overrides | continuation block |
| Import of `Brand.visual_rules` (MKT-1B) into the style guide | when brand entities are wired |
| Figma frame export | as needed |
| Outcome tracking (A vs B winner) | when a publish surface + analytics exist |
| Image-content audit | post-image-gen block |

---

## 12. Audit trail invariants

After a complete strategy + audit + creative + visual cycle, the
chain contains workflow events from the dispatcher (MKT-2A),
`approval_pack` notes from MKT-3B, `creative_pack` notes from MKT-3C
and `visual_pack` notes from MKT-3D. The chain remains valid:

```python
from core.contracts import verify_chain
events = mem.read_audit_events(client_slug)
assert verify_chain(events) == []
```
