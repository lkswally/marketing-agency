# MARKETING-AGENCY-OS

Modular, agent-based marketing operating system. Standalone by default. Optionally bridgeable to ATLAS.

> **Status:** MKT-11E. Real CLI (31 commands), a job execution system, versioned
> approvals, a deterministic campaign pipeline, and a read-only Streamlit portal
> are all implemented and covered by tests. `agents/`, `skills/`, and `workflows/`
> are specifications, not a running orchestration engine — see [What it does NOT
> do yet](#what-it-does-not-do-yet).

---

## What MAOS is today

A deterministic, evidence-driven backend for running a marketing agency's
operational workflow — intake, strategy, compliance/claim audit, creative
drafting, visual direction, execution tasks, and campaign-level jobs — through
a single CLI, with every state change persisted and audited.

- **CLI (`mkt`, 31 commands)** — the only supported entry point today. `cli/main.py`
  dispatches to application services; no HTTP/API layer exists yet (see roadmap).
- **Job execution system** (`core/jobs/`) — `mkt jobs submit/run/list/show/cancel`.
  Jobs move `QUEUED -> RUNNING -> {COMPLETED, FAILED, WAITING_APPROVAL}`. Synchronous,
  single-process (`InlineJobRunner`) — no Redis, no Celery, no external queue.
- **`campaign.run`** — the flagship job operation: runs the full pipeline
  (intake -> strategy -> approval -> creative -> visual -> summary) through the
  job system. Equivalent to the legacy `mkt run-campaign`, which still exists
  and still works standalone.
- **Versioned approvals** (`core/approval/`) — every approval is a real, immutable
  record (`approval_pack/<pack_id>.json`), never a `"current"` singleton. Multiple
  approvals can coexist per client; history is preserved; `mkt approvals list/show`,
  `mkt approve`, `mkt reject` operate on a specific approval id (or resolve
  unambiguously when a client has exactly one).
- **Campaign pipeline** (`core/pipeline/`) — deterministic: intake validation,
  a claim/compliance auditor (22 rules, no LLM), creative + visual drafting,
  execution task packs. Every stage persists its own artifact and emits a
  hash-chained audit event.
- **Analytics/SEO** — `analyze-metrics`, `feedback-plan`, `apply-feedback`,
  `ads-analyze`, `ads-feedback`, `seo-report`: deterministic, LLM-free, read
  persisted metrics snapshots and produce suggestions. No external API calls
  in this layer itself.
- **Portal** (`portal/`, read-only) — a local Streamlit viewer over persisted
  client artifacts. No buttons, no forms, no writes — enforced by a dedicated
  structural test suite. Requires the optional `portal` extra (see below).

## Integrations: real vs dry-run vs spec-only

| Layer | Status |
|---|---|
| GA4 / Search Console / Google Ads connectors (`core/analytics/connectors/`) | **Real SDK integration**, read-only, gated by env credentials. Falls back to "unavailable" cleanly if the SDK or credentials are missing — never fails hard, never fabricates data. |
| Anthropic Claude backend (`--backend claude` on `run-strategy`/`run-campaign`) | **Real SDK integration**, optional. Falls back to a deterministic templated backend if the SDK or `ANTHROPIC_API_KEY` is missing. |
| Notion sync (`notion-sync --write --confirm`) | **Real integration, opt-in.** Dry-run by default; even with the flags, missing `NOTION_TOKEN`/`NOTION_TASKS_DATABASE_ID` falls back to dry-run with a warning. |
| n8n, image providers (`n8n-plan`, `image-provider-plan`, `image-jobs`) | **Dry-run only.** No HTTP call, no credential read, no image generated — these produce the *shape* of a future request for review. |
| Market intelligence adapters (`core/intelligence/`: trends, reddit, youtube, meta ads, competitor monitor) | **Dry-run only** today. |
| ATLAS bridge (`atlas-brief`) | Generates a handoff artifact (JSON/Markdown) for a human to paste into an ATLAS session. No network call, no reach-in to ATLAS. |
| `agents/*.md`, `skills/*.md` | **Spec-only.** Markdown prompt specifications with `status: spec_only` in their own frontmatter. `core/agents/`, `core/skills/` load and validate them (`mkt validate-specs`) — there is no execution engine that runs an agent against these specs. |
| `workflows/*.yaml` (W1–W7) | **Spec-only.** `core/workflows/` parses and lints the phase/gate dependency graph (`mkt list-workflows`, `mkt validate-specs`). No orchestrator executes a workflow phase-by-phase today. |

## What it does NOT do yet

- No HTTP/API server (planned: MKT-11F).
- No frontend / Control Center (the portal is a read-only viewer, not an
  operational UI).
- No automatic job resume — a job that reaches `WAITING_APPROVAL` must be
  resubmitted manually after a decision; there is no `WAITING_APPROVAL -> QUEUED`
  auto-transition.
- No real agent-execution engine over `agents/`/`skills/`/`workflows/` specs.
- No Docker image, no deployment automation (this repo, as of this commit).
- No multi-process/concurrent job execution, no external queue, no locks —
  single-process, sequential, check-then-act only.

## Install

Requires Python **3.11+** (CI runs 3.11 on `ubuntu-latest`).

```bash
git clone <repo-url>
cd MARKETING-AGENCY-OS

python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate

pip install -e ".[dev]"
```

Optional extras, installed only if you need them:

```bash
pip install -e ".[claude]"    # Anthropic SDK, for --backend claude
pip install -e ".[notion]"    # notion-client SDK, for notion-sync --write --confirm
pip install -e ".[portal]"    # Streamlit, for `mkt portal`
```

Copy `.env.example` to `.env` and fill in only the variables you actually need
(all integrations degrade gracefully without them — see the table above).

## Run the CLI

```bash
mkt --help
mkt list-workflows
mkt validate-specs

# End-to-end example
mkt intake --file examples/intake/demo-business.json --client demo-saas --root data/clients
mkt run-campaign --intake examples/intake/demo-business.json --root data/clients --outputs-dir outputs
mkt approvals list --root data/clients
mkt approve --client demo-saas --root data/clients --actor lucas
```

## Run tests

```bash
ruff check .
pytest
```

Do not run more than one `pytest` process concurrently against the same
working tree — file-based test fixtures under `.pytest_tmp/` are not safe
for concurrent runs on Windows.

## Run the portal (optional, read-only)

```bash
pip install -e ".[portal]"
mkt portal --root data/clients --outputs-dir outputs
```

Without the `portal` extra installed, `mkt portal` exits with a clear
install instruction instead of failing unexpectedly.

## Relationship to ATLAS

- **Independent repo**, independent git history.
- ATLAS does NOT depend on MKT. MKT runs **standalone** with zero ATLAS components.
- `core/atlas_bridge/` produces a handoff artifact for a human to carry into
  ATLAS manually — never a live call.

See [`docs/relation-to-atlas.md`](docs/relation-to-atlas.md).

## Repo layout (current)

```
marketing-agency-os/
├─ cli/                 # mkt CLI entry point (cli/main.py, 31 commands)
├─ core/                # domain + application logic, ~28 subpackages
│  ├─ application/      # OperationContext/Result, application services, policies
│  ├─ jobs/             # job execution system (MKT-11C/D)
│  ├─ approval/         # versioned approval history (MKT-11E)
│  ├─ pipeline/          # campaign pipeline orchestrator
│  ├─ agents/, skills/, workflows/   # loaders + linters for the spec-only .md/.yaml specs
│  └─ ...               # analytics, intake, strategy, creative, visual, execution, etc.
├─ agents/              # agent Markdown specs — SPEC_ONLY
├─ skills/              # skill Markdown specs — SPEC_ONLY
├─ workflows/           # workflow YAML specs (W1–W7) — SPEC_ONLY
├─ portal/              # read-only Streamlit viewer (optional extra)
├─ data/clients/        # per-client state (gitignored except .gitkeep)
├─ outputs/             # per-client deliverables (gitignored except .gitkeep)
├─ tests/               # 164+ test files, one dir per core subpackage
├─ docs/                # architecture, inventories, roadmaps, runtime docs
├─ .github/workflows/   # CI (ruff + pytest on ubuntu-latest)
├─ ARCHITECTURE.md
├─ GLOSSARY.md
├─ pyproject.toml
└─ .gitignore
```

## Immediate roadmap

1. **MKT-11F** — HTTP/API foundation over the existing application services (no UI yet).
2. **MKT-12** — Data + Evidence foundation (repository abstraction, Evidence/Recommendation models, groundwork for a future Postgres/Supabase adapter alongside the current JSON file store).
3. **MKT-13** — Website Intelligence (discovery, Lighthouse, tech stack, competitor footprint).
4. **MKT-13E** — Free Marketing Audit (first public-facing product, built on MKT-13).
5. **Control Center** — an operational web UI over the application services, separate from the read-only portal.

## License

Proprietary. All rights reserved.
