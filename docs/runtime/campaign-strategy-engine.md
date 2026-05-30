# Campaign Strategy Engine (MKT-3A)

> Status: **implemented** (MKT-3A).
> Module: `core.strategy`.
> Workflow: `workflows/W7_campaign_strategy_engine.yaml`.
> Backend: `TemplatedStrategyBackend` (deterministic, LLM-free).
> CLI entry: `mkt run-strategy --brief <path> [--client <slug>] [--root <dir>] [--outputs-dir <dir>]`.

The campaign strategy engine is the first end-to-end "useful" surface of
MARKETING-AGENCY-OS. Given a structured input brief about a client + product
+ audience + objectives, it produces a 20-section `CampaignStrategyReport`
in two forms:

1. A Pydantic model persisted to `JsonFileMemory` (kind `campaign_strategy_report`).
2. A rendered Markdown document at `<outputs-dir>/campaign-strategy.md`.

It runs without LLMs, without external APIs, without MCP servers. Outputs
are deterministic — same brief in, same report out.

---

## 1. What it produces

The 20 sections of the report (numbered as in the rendered Markdown):

1. **Resumen ejecutivo** — headline, one-liner, primary objective.
2. **Diagnóstico del negocio** — industry, stage, strengths, challenges,
   opportunities, assumptions made.
3. **Público objetivo** — audience label, demographics, psychographics,
   preferred channels, pains, desired outcomes.
4. **Buyer persona** — archetype, motivations, objections, quotes.
5. **Propuesta de valor** — headline, category, differentiators, proof points.
6. **Benchmark de competidores** — per-competitor strengths/weaknesses,
   differentiating angles, market gaps.
7. **Canales recomendados** — priority table with role and cadence.
8. **Keywords principales** — clusters by intent.
9. **Keywords negativas** — exclusion list.
10. **Hashtags sugeridos** — derived from product + industry + audience.
11. **Estrategia de campaña** — objective, duration, KPIs, funnel focus,
    big idea, narrative arc.
12. **Piezas sugeridas** — table of piece types × channels.
13. **Briefs para flyers / imágenes** — visual concepts + ready-to-paste
    prompts for an image-generation model.
14. **Copies para redes** — drafts per channel with hook / body / CTA.
15. **Secuencia de emails** — 4-email nurture sequence.
16. **Guiones de reels** — 3 short-form video scripts.
17. **Calendario sugerido** — weekly schedule by channel.
18. **Checklist de aprobación** — items with severity (blocker / must / should).
19. **Riesgos / claims a validar** — explicit unverified claims + mitigation.
20. **Próximos pasos** — actionable list.

All 20 sections are guaranteed to be present in any successful run.

---

## 2. Architecture

### 2.1 Pipeline at a glance

```
brief.json
   │
   ▼
StrategyInputBrief (Pydantic)
   │
   ▼
JsonFileMemory.put(client_slug, "strategy_input_brief", "current", ...)
   │
   ▼
MinimalDispatcher.run(W7, client_slug, agent_backend=TemplatedStrategyBackend)
   │
   │ phases sequentially:
   │   intake → diagnose → audience → competitor → positioning →
   │   channels → keywords → creative → calendar → report → approval
   │
   ▼
CampaignStrategyReport persisted to memory
   │
   ▼
render_markdown_report(report) → outputs/campaign-strategy.md
```

### 2.2 Module map (`core/strategy/`)

| File | Purpose |
|------|---------|
| `models.py` | Pydantic models for every output (20 sections + the top-level report) and the input brief. |
| `templates.py` | One deterministic generator function per section. Pure: no I/O, no LLM. |
| `backend.py` | `TemplatedStrategyBackend(AgentBackend)` — routes by `(workflow_id, phase_id)`. Other workflows fall back to `MockAgentBackend`. |
| `pipeline.py` | `StrategyPipeline` — load + persist brief, run dispatcher, read report, render markdown. |
| `renderer.py` | Pure renderer from `CampaignStrategyReport` to Markdown. |

### 2.3 Memory kinds introduced

Each phase persists one or more entities. All keyed by the singleton id
`"current"` (one strategy per client at a time in v1):

```
strategy_input_brief
strategy_diagnosis
strategy_target_audience
strategy_buyer_persona
strategy_competitor_benchmark
strategy_value_proposition
strategy_channel_recommendation
strategy_keyword_plan
strategy_campaign_strategy
strategy_suggested_pieces       # wrapped list
strategy_creative_brief_pack
strategy_social_posts           # wrapped list
strategy_email_sequence
strategy_reels_pack
strategy_schedule
strategy_approval_checklist
strategy_risk_assessment
campaign_strategy_report        # the final report
```

The dispatcher additionally writes `envelope` and `workflow_run` kinds
(MKT-2A).

### 2.4 The workflow (W7)

11 phases (sequential, no parallelization in v1):

| # | Phase | Agent (informational) | Produces |
|---|-------|------------------------|----------|
| 1 | `intake` | mkt-orchestrator | `g_brief_captured` |
| 2 | `diagnose` | mkt-orchestrator | `g_diagnosis_drafted` |
| 3 | `audience` | audience-researcher | `g_audience_research_complete` |
| 4 | `competitor` | competitor-benchmark-agent | `g_competitor_baseline` |
| 5 | `positioning` | brand-strategist | `g_positioning_drafted` |
| 6 | `channels` | channel-advisor-agent | `g_channels_proposed` |
| 7 | `keywords` | keyword-intelligence-agent | `g_keywords_drafted` |
| 8 | `creative` | creative-director | `g_creatives_drafted` |
| 9 | `calendar` | mkt-orchestrator | `g_schedule_drafted` |
| 10 | `report` | mkt-orchestrator | `g_report_drafted` |
| 11 | `approval` | approval-manager | `g_approval_packaged` |

`human_required_at: [approval]` is declared in the YAML. The dispatcher
does not actually halt for approval in v1 — the workflow finishes
end-to-end. The Approval Center wiring is future work (P-1E.5).

---

## 3. The input brief

Schema: `StrategyInputBrief` (`schema_version: strategy-input-brief.v1`).

```json
{
  "schema_version": "strategy-input-brief.v1",
  "client":  { "slug": "...", "name": "...", "industry": "...", "locale": "es-AR" },
  "brand":   { "tone_words": [...], "lexicon_do": [...], "banned_words": [...] },
  "product": { "name": "...", "offer_type": "subscription", "value_props": [...] },
  "objective": "...",
  "audience_hints": [
    { "label": "...", "demographics": {...}, "psychographics": {...},
      "preferred_channels": [...], "estimated_size": 120000 }
  ],
  "constraints": [...],
  "preferred_channels": [...],
  "competitors_known": [{ "name": "...", "url": "...", "strengths": [...], "weaknesses": [...] }],
  "budget_amount": 4500,
  "budget_currency": "USD",
  "deadline": "2026-09-30",
  "duration_weeks": 8,
  "primary_kpi": "qualified_trials",
  "additional_context": "..."
}
```

A complete demo lives in `examples/clients/demo-saas/brief.json`.

### 3.1 Required vs optional

Required:
- `schema_version`, `client.slug`, `client.name`, `product.name`,
  `objective`, at least one `audience_hints` entry.

Optional but encouraged:
- Everything else. Missing fields are absorbed into "assumptions made"
  in the diagnosis section.

---

## 4. CLI usage

```bash
mkt run-strategy \
  --brief examples/clients/demo-saas/brief.json \
  --root data/clients \
  --outputs-dir outputs
```

Exit codes:
- `0` — succeeded; report written.
- `1` — pipeline failed (workflow status not succeeded).
- `2` — invalid input (brief file missing, schema invalid, etc.).

Output to stdout is a JSON summary:

```json
{
  "status": "succeeded",
  "run_id": "...",
  "report_id": "...",
  "client_slug": "demo-saas",
  "report_markdown_path": "outputs/campaign-strategy.md",
  "envelope_count": 11
}
```

---

## 5. Determinism guarantees

- Same brief → same artifact paths in markdown output.
- Same brief → same content per section (modulo entity ids and the
  `generated_at` timestamp, which the caller controls).
- Generators are pure functions of their inputs. Anything random comes
  from `new_id()` (UUID4) — only used for opaque ids.
- No network calls. No file reads outside `core.strategy` or `cli`.

This is why the engine ships with `MockAgentBackend`-level safety: no
spawn, no API, no credentials.

---

## 6. Limitations

This is v1. The trade-offs are explicit:

- **Outputs are template-driven, not creative.** A real campaign run by
  a real team will produce more nuanced copy. The system is correct and
  complete, not brilliant.
- **No live data.** Keywords have no volumes; competitor benchmark is
  only as good as the human-provided input.
- **No claim validation.** Section 19 lists unverified claims; the
  compliance subsystem (MKT-3B) is the next block to gate them.
- **No actual asset generation.** Image prompts are produced, no image
  is rendered. Reels scripts are produced, no video is edited.
- **One strategy per client at a time.** The singleton id `"current"`
  means a new run overwrites the previous one. Versioning is a future
  block.
- **Sequential.** No parallelization across phases.

---

## 7. What gets persisted

After a successful run for client `demo-saas`:

```
data/clients/demo-saas/
├── _meta.json
├── strategy_input_brief/current.json
├── strategy_diagnosis/current.json
├── strategy_target_audience/current.json
├── strategy_buyer_persona/current.json
├── strategy_competitor_benchmark/current.json
├── strategy_value_proposition/current.json
├── strategy_channel_recommendation/current.json
├── strategy_keyword_plan/current.json
├── strategy_campaign_strategy/current.json
├── strategy_suggested_pieces/current.json
├── strategy_creative_brief_pack/current.json
├── strategy_social_posts/current.json
├── strategy_email_sequence/current.json
├── strategy_reels_pack/current.json
├── strategy_schedule/current.json
├── strategy_approval_checklist/current.json
├── strategy_risk_assessment/current.json
├── campaign_strategy_report/current.json
├── envelope/
│   └── <uuid>.json   × 11
├── workflow_run/
│   └── <run_id>.json
└── audit/
    ├── YYYY-MM-DD.jsonl
    └── _chain_tail.txt
```

`outputs/campaign-strategy.md` is the rendered deliverable.

---

## 8. What's out of scope (and the block that opens it)

| Concern | Block |
|---------|-------|
| LLM-backed generation | dedicated block, requires Claude Code safety boundaries |
| Live data (GA4, GSC, etc.) | MKT-MCP-3+ |
| Claim audit enforcement | MKT-3B |
| Approval Center halt-and-wait | MKT-3B / MKT-2C continuation |
| Real image generation | post-MCP, post-replicate |
| Versioned strategies per client | future block |
| Parallel phase execution | with real backend approval |
| Email send / social publish | MKT-MCP-8 (via n8n) |
