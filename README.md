# MARKETING-AGENCY-OS

Modular, agent-based marketing operating system. Standalone by default. Optionally bridgeable to ATLAS.

> **Status:** MKT-1A (foundations). No runtime code yet. Specs and architectural decisions only.

---

## What it is

An operating system for running a marketing agency:

- Audience research
- Competitor analysis
- Strategy
- Campaign creation
- Copywriting
- **Claim compliance & audit** (first-class subsystem)
- Brand voice memory
- Distribution
- Analytics

Not a "post generator." A system with phases, gates, agents, workflows and persistent memory.

## What it is NOT

- Not a SaaS or UI product (MVP has no web UI)
- Not a CRM or billing platform
- Not a clone of ATLAS — inherits **philosophy**, not code
- Not coupled to Claude Code — agents are Markdown specs (runnable by Claude Code today, by other runtimes later)

## Relationship to ATLAS

- **Independent repo**, independent git history.
- ATLAS does NOT depend on MKT.
- MKT can run **standalone** with zero ATLAS components.
- A future opt-in `bridge/` adapter lets ATLAS invoke MKT, never the inverse.
- Engram namespace is separate: `marketing-agency-os/*` (never `atlas/*`).

See [`docs/relation-to-atlas.md`](docs/relation-to-atlas.md).

## Quick start (current block: MKT-1A)

```bash
# Clone (when remote exists)
cd D:\ProyectosIA\MARKETING-AGENCY-OS

# Set up dev env
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# Verify
ruff check .
pytest
```

In MKT-1A there is no runtime to execute yet. The repo only ships:

- Architectural decisions (12) — [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Domain glossary — [`GLOSSARY.md`](GLOSSARY.md)
- Relation to ATLAS — [`docs/relation-to-atlas.md`](docs/relation-to-atlas.md)

## Roadmap (block-based)

| Phase | Block | Goal |
|-------|-------|------|
| 1 | **MKT-1A** | Repo scaffolding + 12 architectural decisions (this block) |
| 1 | MKT-1B | Domain model (Client, Brand, Audience, Campaign, Claim, ...) |
| 1 | MKT-1C | Contracts: Return Envelope, Phase Gates, Audit Trail, Claim Audit |
| 1 | MKT-1D | Memory backend abstract + JSON local default |
| 2 | MKT-2A | Minimal dispatcher (one agent, one phase, end-to-end) |
| 2 | MKT-2B | First agent: `brand-voice-keeper` |
| 2 | MKT-2C | Engram adapter (opt-in second backend) |
| 3 | MKT-3A | Claim-validator subsystem (first-class compliance) |
| 3 | MKT-3B | Compliance enforcement in envelope |
| 4 | MKT-4A/B/C | Research agents: audience, competitor, strategist |
| 5 | MKT-5A/B/C | Production agents: copywriter, creative-director, first E2E workflow |
| 6 | MKT-6A/B/C | Distribution, analytics, ATLAS bridge |

Each block has explicit acceptance criteria. No block ships without passing its phase gate.

## Repo layout (current)

```
marketing-agency-os/
├─ docs/
│  ├─ contracts/        # (MKT-1C) Envelope, Phase Gates, Audit Trail specs
│  ├─ decisions/        # ADRs — one file per architectural decision
│  └─ relation-to-atlas.md
├─ data/clients/        # Per-client state (gitignored except .gitkeep)
├─ outputs/             # Per-client deliverables (gitignored)
├─ assets/clients/      # Per-client binary assets (gitignored)
├─ tests/
├─ .github/workflows/   # CI
├─ ARCHITECTURE.md
├─ GLOSSARY.md
├─ README.md
├─ pyproject.toml
└─ .gitignore
```

Folders for `core/`, `agents/`, `skills/`, `workflows/`, `playbooks/`, `integrations/`, `bridge/`, `config/` are intentionally **NOT created in MKT-1A**. They appear when their block lands. No empty scaffolding.

## License

Proprietary. All rights reserved.
