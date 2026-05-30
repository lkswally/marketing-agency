# Creative Factory Pack (MKT-3C)

> Status: **implemented** (MKT-3C).
> Module: `core.creative`.
> Backend: deterministic templates (no LLM, no image API, no publishing).
> Contract: `creative-pack.v1`.
> CLI entry: `mkt build-creatives --client <slug>`.

The Creative Factory Pack is the operational sibling of the Campaign
Strategy Report (MKT-3A). Where the strategy report is the strategic
deliverable a reviewer reads, the **CreativeAssetPack** is the working
artifact the creative team picks up: structured assets with A/B
variants, per-piece publishing state derived from the Approval Pack
(MKT-3B), and a per-piece dated calendar.

The pack carries no images, sends no emails, and never publishes
anything. The terminal positive state is `READY_FOR_PUBLISH`.

---

## 1. What it produces

For each campaign cycle, the pack ships:

- **Social posts** — up to 6 posts (top 3 channels × 2 each), each with
  2 hook variants and 2 CTA variants, plus a cross-post caption and
  hashtags.
- **Emails** — the full nurture sequence with 2 subject line variants
  per email.
- **Reels scripts** — title, 2 hook variants, beats, voiceover,
  on-screen text, CTA, target duration.
- **Flyers copy** — 1:1, 4:5 and 9:16 formats, each with 2 headline
  variants, subhead, body, CTA.
- **Image prompts** — ready-to-paste prompts (with negative prompts,
  palette, accessibility notes) for any future image generator.
- **Calendar** — every piece gets a concrete date inside the campaign
  window.
- **Per-asset checklist** — operational steps tailored to the asset's
  state.

The complete `CreativeAssetPack` is persisted to memory and rendered to
both Markdown (`outputs/creative-pack.md`) and JSON
(`outputs/creative-pack.json`).

---

## 2. State derivation

Each asset's state is *derived* from the Approval Pack (MKT-3B), not
authored:

| Condition | Asset state |
|-----------|-------------|
| No Approval Pack persisted | `NEEDS_REVIEW` (conservative default) |
| `ApprovalPack.blocks_publish == True` | `BLOCKED` |
| `ApprovalPack.state == APPROVED` AND not blocking | `READY_FOR_PUBLISH` |
| Overall severity in {risky, unsafe} AND not approved | `NEEDS_REVIEW` (via blocks_publish=True → BLOCKED) |
| Otherwise (e.g. caveat-only or safe) | `DRAFT` |

The state machine intentionally omits `PUBLISHED`. Publishing is a
runtime concern that lives outside MKT-3C and only opens up
post-MKT-MCP-8 (n8n trigger / email send adapter / social adapter), all
of which MUST honor `pack.blocks_publish`.

---

## 3. Architecture

```
CampaignStrategyReport (MKT-3A)
        +
ApprovalPack (MKT-3B, optional)
        │
        ▼
CreativeFactory.build(report, approval_pack)
        │
        │ deterministic templates
        │   + variant generators
        │   + state derivation
        │   + per-piece calendar
        │
        ▼
CreativeAssetPack (state=derived)
        │
        ▼
CreativeFactory.persist(pack)
        │
        │ writes:
        │   data/clients/<slug>/creative_asset_pack/current.json
        │ emits audit event:
        │   {action: created|updated, ...}
        │
        ▼
Markdown + JSON written to outputs/
```

### 3.1 Module map (`core/creative/`)

| File | Purpose |
|------|---------|
| `models.py` | Pydantic models: `CreativeAssetPack` + the five asset kinds + variant + calendar models. |
| `factory.py` | `CreativeFactory` + state derivation + variant generators + `build_and_persist` helper. |
| `calendar.py` | Pure `schedule_assets(...)` — assigns dates per asset using channel-specific weekdays. |
| `renderer.py` | Pure Markdown renderer. |

### 3.2 Memory kind

- `creative_asset_pack` — singleton id `"current"` per client.

### 3.3 Audit events

Every `persist` emits `event_type=note` with `payload.creative_pack.action`
in `{"created", "updated"}`. The action discriminator mirrors MKT-3B's
approval-pack events, so an `audit-trail.v2` promotion can bundle both
families in a single contract bump.

---

## 4. Variant generators

Per-asset variants are produced by deterministic template rotations:

| Asset | Variant axis | Variants per asset |
|-------|--------------|---------------------|
| Social post | `hook` (`contrast` / `curiosity`) + `cta` (`direct` / `low_friction`) | 2 + 2 |
| Email | `subject_line` (`direct` / `question`) | 2 |
| Reels | `hook` (`curiosity` / `data`) | 2 |
| Flyer | `headline` (`benefit` / `point_of_view`) | 2 |

Same input → same variants. The trade is real: copy will not be witty
or contextual. The strategic point of v1 is to fix the shape (axes,
counts, deterministic IDs A/B) so a future LLM-backed factory swaps
generators in without changing the data model.

---

## 5. Calendar

`core/creative/calendar.py::schedule_assets` schedules each piece
deterministically:

- Emails land at `start_date + send_after_days` (clamped to `end_date`).
- Social posts cycle through each channel's default weekdays
  (LinkedIn: Tue + Thu, X: Mon/Wed/Fri, Instagram: Tue + Fri, etc.).
- Reels land on Wednesdays.
- Flyers land on Tuesdays.

The output is sorted by date so a reviewer reads a chronologically
sequenced plan. Every asset gets its `scheduled_for` backfilled by the
factory after the calendar is built.

---

## 6. CLI usage

```bash
# Prerequisite: strategy + audit already persisted.
mkt run-strategy --brief examples/clients/demo-saas/brief.json --audit

# Build the creative pack:
mkt build-creatives --client demo-saas
```

Exit codes:

- `0` — pack produced.
- `2` — no persisted `CampaignStrategyReport` for the client.
- `3` — `--require-approval` was set AND `ApprovalPack.blocks_publish == True`.

Output to stdout is a JSON summary. Disk side effects:

- `outputs/creative-pack.md` — full Markdown rendering.
- `outputs/creative-pack.json` — same content in JSON.
- `data/clients/<slug>/creative_asset_pack/current.json` — persisted
  Pydantic dump.
- An audit event recording the action.

---

## 7. Programmatic API

```python
from pathlib import Path

from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline
from core.approval import ApprovalPackBuilder
from core.creative import CreativeFactory, render_markdown_pack

mem = JsonFileMemory(Path("data/clients"))

report = StrategyPipeline(memory=mem).run_from_path(
    "examples/clients/demo-saas/brief.json"
).report

builder = ApprovalPackBuilder(memory=mem)
ap = builder.build_from_report(report)
builder.persist(ap)

factory = CreativeFactory(memory=mem)
pack = factory.build(report, ap)
factory.persist(pack)

print(render_markdown_pack(pack))
```

---

## 8. Layering

```
CampaignStrategyReport          (MKT-3A, strategic)
        │ feeds
        ▼
ApprovalPack                    (MKT-3B, compliance)
        │ derives state
        ▼
CreativeAssetPack               (MKT-3C, operational)
        │ blocks_publish honored by
        ▼
Future publishers               (MKT-MCP-8 — not implemented)
```

Each layer is a separate package (`core/strategy/`, `core/approval/`,
`core/creative/`). They share `core.contracts` / `core.domain` /
`core.memory` but do not import each other beyond their immediate
upstream input.

---

## 9. The "never published" guarantee

The `CreativeAssetState` enum exposes:

```python
DRAFT
NEEDS_REVIEW
READY_FOR_PUBLISH
BLOCKED
```

There is no `PUBLISHED` value. Tests pin this property explicitly:

```python
def test_no_asset_is_ever_published(...):
    values = {s.value for s in CreativeAssetState}
    assert "published" not in values
```

A future publisher will introduce a *separate* publication record
(e.g. `PublicationLog`) and update assets via a domain event. It will
NOT mutate the pack's state model. The pack is the request; the
publication log is the receipt.

---

## 10. Limitations (and where they open)

| Concern | Block |
|---------|-------|
| LLM-backed copy generation (better A/B angles, brand-tone respect) | dedicated block, post-Claude Code safety |
| Real image generation from the prompts | post-MCP / Replicate |
| ICS / Google Calendar export | as needed |
| Versioned packs (history / diff) | as needed |
| Per-channel format adaptation (Reels vs IG Story vs LinkedIn carousel) | continuation block |
| Actually publishing the assets | MKT-MCP-8 + per-source adapters |
| Per-pack outcome tracking (A vs B winner) | when a publish surface exists |

---

## 11. Audit trail invariants

After a complete strategy + audit + build-creatives cycle, the chain
contains workflow events from the dispatcher (MKT-2A), `approval_pack`
notes from MKT-3B and `creative_pack` notes from MKT-3C. The chain
remains valid:

```python
from core.contracts import verify_chain
events = mem.read_audit_events(client_slug)
assert verify_chain(events) == []
```
