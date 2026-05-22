# ARCHITECTURE — MARKETING-AGENCY-OS

> Closed architectural decisions for MKT-1A. Each decision is binding for downstream blocks unless an ADR in `docs/decisions/` supersedes it.

Format per decision: **Context → Decision → Alternatives rejected → Consequences**.

---

## D1 — Agent execution runtime

**Context.** Agents need to be invocable both interactively (developer working with Claude Code) and programmatically (future scheduled workflows, CI, bridge from ATLAS).

**Decision.** Agents are **Markdown specs** in `agents/*.md` (frontmatter + body, same shape as ATLAS subagents). Primary runtime is **Claude Code subagent spawns** via the `Agent` tool. A thin Python CLI wrapper (added in MKT-2A) can read the same specs and invoke them via the Anthropic SDK for non-interactive runs. **One spec, two runtimes.**

**Alternatives rejected.**
- Python-only with classes per agent — too rigid, loses Claude Code ergonomics.
- Claude Code only — blocks future scheduling, CI, and headless invocation.

**Consequences.**
- Agent specs must be portable: no Claude-Code-specific tool calls hardcoded in the spec body.
- The Python wrapper must respect the same Return Envelope contract as Claude Code spawns.

---

## D2 — Memory backend

**Context.** MKT must run standalone without Engram, but should benefit from Engram when available.

**Decision.** Define an **abstract `Memory` interface** (MKT-1D) with two adapters:
1. **`JsonFileMemory`** (default) — persists to `data/clients/<slug>/.memory/*.json`. Always available, zero deps.
2. **`EngramMemory`** (opt-in, MKT-2C) — reads/writes Engram via MCP. Activated by env var `MKT_MEMORY_BACKEND=engram`.

Engram is NEVER imported from `core/`. It lives in `integrations/engram_adapter.py` and is loaded lazily.

**Alternatives rejected.**
- Engram-only — breaks standalone guarantee.
- SQLite — adds runtime dep without solving the "shared memory across sessions" problem Engram solves.

**Consequences.**
- All memory access goes through the abstract interface. No direct file or MCP calls from agents.
- Engram namespace strictly `marketing-agency-os/<client-slug>/<topic>`. Never collides with `atlas/*`.

---

## D3 — Multi-tenant from day 1

**Context.** A marketing agency manages many clients. Retrofitting multi-tenant is expensive.

**Decision.** **Every artifact is scoped to a client slug from MKT-1A.** Layout:
- `data/clients/<slug>/` — state, memory cache, briefs
- `outputs/<slug>/` — deliverables (copies, reports)
- `assets/clients/<slug>/` — binaries (logos, images, PDFs)
- Engram topic keys: `marketing-agency-os/<slug>/<topic>`

A `default` slug is reserved for testing and bootstrap. No client data is global.

**Alternatives rejected.**
- Single-tenant first, refactor later — every refactor compounds.
- Multi-repo per client — operational nightmare for an agency.

**Consequences.**
- Every agent spec must accept a `client_slug` parameter.
- Cross-client work (e.g., industry trends) lives under a special `_shared` slug, never global.

---

## D4 — Compliance is a subsystem, not a skill

**Context.** Hallucinated claims in marketing copy create legal/financial risk. Treating compliance as one skill among many trivializes it.

**Decision.** **Claim validation is a first-class subsystem** (MKT-3A) with:
- Its own data model: `Claim`, `Evidence`, `Verdict`, `Severity`
- Its own append-only audit trail
- Mandatory hook: any agent producing copy with factual assertions MUST emit a `claims_audit` block in its Return Envelope
- Dispatcher rejects envelopes missing required claims audit when output contains assertions

**Alternatives rejected.**
- Skill-level validator — too easy to bypass.
- Post-hoc review — claims must be validated **before** output is persisted.

**Consequences.**
- Adds latency and complexity to every production agent.
- Required: a catalogue of evidence sources per client (whitelisted URLs, internal docs).

---

## D5 — Workflows vs Playbooks

**Context.** The baseline plan listed both `workflows/*.yaml` and `playbooks/*.json` without distinguishing them.

**Decision.**
- **Workflow** = an executable DAG of agents and gates. Format: YAML. Example: `W1_onboarding.yaml` orchestrates `audience-researcher → competitor-analyst → strategist → brand-voice-keeper`.
- **Playbook** = a parameterized recipe for a marketing motion (e.g., "evergreen lead gen for B2B SaaS"). Format: JSON. References workflows and provides defaults. Plug-and-play across clients.

Workflows are **how**. Playbooks are **what**.

**Alternatives rejected.**
- Collapse into one — loses the reuse layer.
- Drop playbooks entirely — agency loses leverage; everything becomes bespoke.

**Consequences.**
- Two schemas to define and validate (MKT-1C contracts will cover both).

---

## D6 — Bridge to ATLAS — opt-in contract

**Context.** ATLAS may want to invoke MKT (e.g., orquestador delegates a copywriting task). MKT must never reach into ATLAS.

**Decision.** A single module `bridge/atlas_adapter.py` (MKT-6C) exposes a versioned contract:
- Activation: env var `MKT_BRIDGE_ATLAS=1`. Off → adapter is not imported.
- Surface: a small set of named operations (`run_workflow`, `validate_claims`, `get_brand_voice`).
- Versioning: contract has its own semver (`bridge.v1`). Breaking changes bump major.
- Kill-switch: env var `MKT_BRIDGE_ATLAS=0` disables instantly.

**MKT never imports from ATLAS.** The bridge is a one-way ingress.

**Alternatives rejected.**
- Tight coupling via shared Python imports — destroys independence.
- HTTP API only — overkill for a local-first system.

**Consequences.**
- The bridge contract is documentation-first (markdown spec before code).
- ATLAS-side integration is a separate concern handled in ATLAS's repo, never here.

---

## D7 — Folder taxonomy

**Context.** `data/`, `outputs/`, `assets/` are easy to confuse.

**Decision.**
- **`data/`** — **state** the system reads and updates (briefs, memory cache, intermediate analysis). Mostly JSON/YAML.
- **`outputs/`** — **deliverables** intended for the client (final copies, reports, exported decks). Mostly Markdown/PDF/HTML.
- **`assets/`** — **binaries** owned by or about the client (logos, source images, brand kits). Mostly opaque files.

All three are per-client (`<root>/clients/<slug>/`) and gitignored by default.

**Alternatives rejected.**
- Flat `clients/<slug>/{data,outputs,assets}/` — equivalent but harder to glob ("all outputs across clients").

**Consequences.**
- Three top-level folders to remember. ADR may revisit if friction emerges.

---

## D8 — Secrets management

**Context.** API keys (Anthropic, Resend, GA4, Notion) must never be committed.

**Decision.**
- Local development: `.env` file at repo root, loaded via `os.environ` (no `python-dotenv` unless justified later).
- Template: `.env.example` checked in (no secrets, just keys).
- Per-client secrets: `data/clients/<slug>/.env` (gitignored).
- CI: GitHub Actions secrets.
- No secret ever logged, even in DEBUG.

**Alternatives rejected.**
- `python-dotenv` — adds runtime dep for marginal convenience.
- Vault / cloud secret manager — premature for a local-first MVP.

**Consequences.**
- Devs must `source .env` (or equivalent shell helper) manually. Acceptable friction.

---

## D9 — CI — minimal from day 1

**Context.** Letting CI accrete is how projects end up with no CI.

**Decision.** GitHub Actions workflow in MKT-1A runs on every push and PR:
1. `ruff check .`
2. `pytest -m "not integration"`

That is it. Coverage thresholds, type checks, security scans are added per block when relevant.

**Alternatives rejected.**
- No CI until MKT-2 — too late, drift starts immediately.
- Full pipeline (cov, mypy, bandit, etc.) — premature.

**Consequences.**
- Every PR runs CI in <60s. Cheap, hard to ignore.

---

## D10 — Testing policy

**Context.** Tests added "later" are tests never added.

**Decision.**
- **`pytest`** is the test runner.
- **Three test categories**, marked:
  - **unit** (default) — pure functions, no I/O.
  - **contract** — verify Return Envelope, Phase Gates, Audit Trail compliance. Required to pass before block PR merges.
  - **integration** — hit external systems (Engram, APIs). Skipped in CI by default.
- Each block must add tests for the artifacts it ships. No code-only PRs after MKT-1D.
- Coverage is **observed, not enforced**, until MKT-3 (compliance subsystem) — then ≥80% on `claim_validator/`.

**Alternatives rejected.**
- 100% coverage gate — produces test theater.
- No coverage at all — invites rot.

**Consequences.**
- Slower per-block velocity, higher per-block confidence.

---

## D11 — Logging

**Context.** `print()` debugging poisons production logs.

**Decision.** Structured JSON logging via Python's stdlib `logging` configured with a JSON formatter (MKT-1D ships the config). No `print()` in `core/`, `agents/`, `skills/`, `integrations/`. Ruff rule enforces it.

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Default in dev: `INFO`. Default in CI/prod: `WARNING`.

**Alternatives rejected.**
- `structlog` — nice but adds dep; revisit if stdlib JSON proves painful.

**Consequences.**
- Slightly more boilerplate per logger. Worth it.

---

## D12 — Versioning

**Context.** Repo version, contract version, and agent spec version all evolve at different rates.

**Decision.**
- **Repo**: semver in `pyproject.toml`. Starts `0.1.0`. Goes `1.0.0` after MKT-6C ships.
- **Contracts** (Envelope, Phase Gates, Audit Trail, Claim Audit, Bridge): each has independent semver, declared in its spec file (`docs/contracts/envelope.md` header). Envelopes carry a `contract_version` field.
- **Agent specs**: each agent `.md` has a `version` in frontmatter. Bumped on breaking changes.

**Alternatives rejected.**
- Single repo version covers everything — couples too much; a contract bump shouldn't force a repo major.

**Consequences.**
- Three version axes to track. Documented and enforced in MKT-1C.

---

## Open questions (to be closed in later blocks)

- **OQ-1** (MKT-1B) — exact field list of `Brand` and `Audience` entities.
- **OQ-2** (MKT-2C) — Engram topic key conventions for cross-client analytics.
- **OQ-3** (MKT-3A) — evidence source whitelist format and revocation policy.
- **OQ-4** (MKT-6C) — exact list of operations exposed by `bridge.v1`.

---

## ADR process

When a decision needs to change, do not edit this file. Create a new ADR in `docs/decisions/NNNN-title.md` that supersedes the relevant D-entry. This file is updated by reference (a "Superseded by ADR-NNNN" note), never overwritten.
