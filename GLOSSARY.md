# GLOSSARY

Canonical vocabulary for MARKETING-AGENCY-OS. If a term is not here, it does not exist in the system yet.

---

### Agent
A Markdown spec in `agents/*.md` describing a role (e.g. `copywriter`, `strategist`). Executable by Claude Code subagent spawn or by the Python CLI wrapper. Always returns a Return Envelope.

### Asset
A binary file owned by or about a client (logo, source image, PDF deck, brand kit). Lives in `assets/clients/<slug>/`. Never committed.

### Audience
A defined segment of people targeted by a campaign. Has demographic, psychographic, and channel attributes. Modeled formally in MKT-1B.

### Audit Trail
Append-only log of significant events (envelope receipts, gate transitions, claim verdicts). One file per client per day: `data/clients/<slug>/audit/YYYY-MM-DD.jsonl`. Never edited, only appended.

### Brand
The identity attached to a client: voice, tone, vocabulary do/don't lists, visual rules. Modeled in MKT-1B.

### Brand Voice
The verbal expression of a brand: lexicon, cadence, taboo words, allowed claims style. Managed by the `brand-voice-keeper` agent.

### Bridge (ATLAS Bridge)
Opt-in adapter in `bridge/atlas_adapter.py` (MKT-6C) that lets ATLAS invoke MKT operations. One-way: ATLAS → MKT only. Versioned (`bridge.v1`).

### Brief
The input document that kicks off a workflow. Describes objective, audience, constraints, deadline. Lives in `data/clients/<slug>/briefs/`. JSON or Markdown.

### Campaign
A bounded marketing effort with goal, audience(s), channels, timeline and assets. Modeled in MKT-1B.

### Channel
A distribution surface (email, IG, LinkedIn, paid search, podcast, etc.). Modeled in MKT-1B.

### Claim
A factual assertion in a marketing output ("3× faster", "GDPR-compliant", "used by Fortune 500"). MUST be backed by Evidence. Validated by the claim-validator subsystem.

### Claims Audit
A required envelope block for any agent producing copy with claims. Lists each Claim, its Evidence, its Verdict, and its Severity. Mandatory from MKT-3B onward.

### Client
A real-world customer of the agency. Identified by a URL-safe `slug` (e.g. `acme-corp`). All client data is scoped under this slug.

### Contract
A versioned spec defining a protocol: Return Envelope, Phase Gates, Audit Trail, Claim Audit, Bridge. Lives in `docs/contracts/`. Each has its own semver.

### Dispatcher
The thin orchestrator in `core/dispatcher.py` (MKT-2A) that loads workflows, spawns agents, validates envelopes, runs phase gates, and writes the audit trail. Not an agent; it is plumbing.

### Engram
External persistent memory (MCP server). **Optional** backend in MKT, activated via `MKT_MEMORY_BACKEND=engram`. Topic key prefix: `marketing-agency-os/`.

### Envelope (Return Envelope)
The standard response format every agent must return. Contains `status`, `task`, `artifacts`, `memory_writes`, `claims_audit` (when applicable), `notes`, `contract_version`. Specified in `docs/contracts/envelope.md` (MKT-1C).

### Evidence
A pointer to a source that supports a Claim. Has type (`url`, `internal_doc`, `dataset`, `quote`), location, retrieval date, and trust level.

### Gate (Phase Gate)
A predicate evaluated between phases of a workflow. If the gate fails, the workflow halts with explicit blockers. Specified in `docs/contracts/phase-gates.md`.

### Memory
Persistent state keyed by `(client_slug, topic)`. Accessed through the abstract `Memory` interface (MKT-1D). Two backends: `JsonFileMemory` (default), `EngramMemory` (opt-in).

### Output
A deliverable intended for the client (final copy, monthly report, exported deck). Lives in `outputs/<slug>/`. Never committed.

### Playbook
A parameterized recipe for a marketing motion (e.g. "evergreen lead gen for B2B SaaS"). JSON in `playbooks/`. References Workflows and provides default parameters. Reusable across clients.

### Severity (of a Claim verdict)
Ordinal level: `safe` < `caveat` < `risky` < `unsafe`. `unsafe` blocks output emission. `risky` requires human override.

### Skill
A focused capability used by one or more agents (e.g. `headline-generator`, `keyword-cluster`). Lives in `skills/<name>/`. Smaller than an agent; usually a function plus a prompt template.

### Slug
A URL-safe lowercase identifier with dashes (e.g. `acme-corp`, `nothing-bay`). Used to scope clients, campaigns and other tenanted entities. Reserved: `default`, `_shared`.

### Status (envelope field)
One of: `completado`, `fallido`, `PASS`, `FAIL`. `PASS`/`FAIL` reserved for validator-type agents (claim-validator, future QA agents).

### Verdict (claim)
Output of claim validation: `verified`, `partial`, `unverified`, `contradicted`. Combined with Severity to decide whether the output ships.

### Workflow
An executable DAG of agents and gates, defined in `workflows/*.yaml`. Example: `W1_onboarding` runs `audience-researcher → competitor-analyst → strategist → brand-voice-keeper`. Workflows describe **how**; Playbooks describe **what**.
