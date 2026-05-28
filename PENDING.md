# PENDING — Items detected but deferred

Things noticed during a block that are out of scope for that block. Each item
must say which block introduced it and which (estimated) block will resolve it.

---

## From MKT-1B (domain model)

### P-1B.1 — Schema versioning / migration policy
- **Introduced:** MKT-1B
- **Why deferred:** No persistence layer exists yet. Migration only matters once we store entities.
- **Resolves at:** MKT-1D (Memory backend) at the earliest, more likely a dedicated block before MKT-3.
- **Sketch:** Each persisted entity payload should carry the `domain-model.vN` it was written with. The repository layer is responsible for upgrading on read.

### P-1B.2 — Cross-entity referential integrity  ✅ RESOLVED in MKT-1D
- **Introduced:** MKT-1B
- **Resolved at:** MKT-1D — `core/memory/referential_integrity.py` with `REFERENCE_MAP`, `find_missing_references`, `check_client_integrity`.
- **Notes:** Pure helpers; do not raise. Callers decide enforcement.

### P-1B.3 — JSON Schema export to disk for external consumers
- **Introduced:** MKT-1B
- **Why deferred:** Optional. No external consumer exists yet.
- **Resolves at:** MKT-1C (contracts block) or on-demand.
- **Sketch:** `python -m core.domain export-schemas > docs/contracts/schemas/*.json`.

### P-1B.4 — Seed / fixture loader CLI
- **Introduced:** MKT-1B
- **Why deferred:** No runtime in MKT-1B. Demo fixtures live in `tests/domain/conftest.py` only.
- **Resolves at:** MKT-2A (minimal dispatcher).
- **Sketch:** A CLI that takes the test fixtures and writes a demo client to `data/clients/default/`.

### P-1B.5 — `.env.example` (carry-over from MKT-1A)
- **Introduced:** MKT-1A (hook blocked write).
- **Why deferred:** `config-protection.js` hook refuses to let Claude write `.env*` files.
- **Resolves at:** anytime (manual user action).
- **Sketch:** Template should include `MKT_MEMORY_BACKEND=json`, `MKT_LOG_LEVEL=INFO`, `MKT_BRIDGE_ATLAS=0`. Future blocks will append provider keys.

### P-1B.6 — Engram session registration for `marketing-agency-os` project
- **Introduced:** MKT-1A (Engram rejected the project name).
- **Why deferred:** `.engram/config.json` is now in place but Engram won't register the project until Claude Code is opened from the repo root once.
- **Resolves at:** anytime (manual user action — open Claude Code from `D:\ProyectosIA\MARKETING-AGENCY-OS\`).

---

## From MKT-1C (operational contracts)

### P-1C.1 — Audit trail JSONL persistence  ✅ RESOLVED in MKT-1D
- **Introduced:** MKT-1C
- **Resolved at:** MKT-1D — `JsonFileMemory.append_audit_event` / `read_audit_events` / `last_audit_hash`. Daily UTC rotation, `_chain_tail.txt` for O(1) tail lookup.
- **Notes:** Retention configurable per client is NOT in v1; revisit if needed.

### P-1C.2 — Strictness mode enforcers (qa_strict / dev_strict / design_strict / claim_strict)
- **Introduced:** MKT-1C
- **Why deferred:** Modes are caller policy (D-3.8), not schema. They belong in the dispatcher.
- **Resolves at:** MKT-2A (minimal dispatcher) for the first mode, the rest as agents land.

### P-1C.3 — `predicate_kind` evaluators
- **Introduced:** MKT-1C
- **Why deferred:** The contract declares the kinds; evaluating them needs runtime state (envelopes seen, memory, filesystem).
- **Resolves at:** MKT-2A onwards. Each block that introduces a phase ships the predicate(s) it needs.

### P-1C.4 — Hash classifier fragility
- **Introduced:** MKT-1C
- **Why deferred:** `_classify` in `validators.py` matches on Pydantic error message substrings ("hash mismatch", "timezone-aware", "duplicate"). If the message wording in our own validators changes, classification silently degrades.
- **Resolves at:** as needed. Tests pin the current behavior. A more robust path would surface a custom error type from each `model_validator`, but that's overhead disproportionate to the risk at this stage.

### P-1C.5 — Human override field for blocked claim audits
- **Introduced:** MKT-1C
- **Why deferred:** The `blocks_emission` policy is strict by design in `v1`. A human override (signed acknowledgement of a risky claim) is a workflow concern.
- **Resolves at:** MKT-3B (claim audit enforcement in envelope) at earliest.

### P-1C.6 — External anchoring of audit chain
- **Introduced:** MKT-1C
- **Why deferred:** The hash chain detects in-place tampering but not a wholesale replay. Anchoring (e.g. publishing daily root hashes to a trusted store) is out of scope.
- **Resolves at:** not scheduled. Revisit when compliance requirements demand it.

---

## From MKT-1D (storage / memory layer + referential integrity)

### P-1D.1 — Dynamic validation of `Metric.subject_id`
- **Introduced:** MKT-1D
- **Why deferred:** `Metric.subject_type` selects the target kind dynamically (client / competitor / channel / campaign / asset / persona / audience). A simple `(field, target_kind)` rule in `REFERENCE_MAP` cannot express this.
- **Resolves at:** as needed. Likely a dedicated helper `validate_metric_subject(memory, metric)` in `core/memory/referential_integrity.py`.

### P-1D.2 — Schema migration runner
- **Introduced:** MKT-1D (carries over from P-1B.1)
- **Why deferred:** `_meta.json` carries `contract_version` so old folders are detectable, but `v1` has nothing to migrate from. When the first breaking change to either `memory.v1` or `domain-model.v1` lands, the runner will live in `core/memory/migrations/`.
- **Resolves at:** TBD per first migration need.

### P-1D.3 — Cross-process / cross-host concurrency
- **Introduced:** MKT-1D
- **Why deferred:** `memory.v1` explicitly assumes single-process sequential use. The audit chain tail is not locked across processes.
- **Resolves at:** when a multi-worker dispatcher or web entry point appears. Likely requires either a file-lock layer (`fcntl` / `msvcrt.locking`) or a swap to a backend with native concurrency (Postgres, Redis, Engram).

### P-1D.4 — Audit retention / compaction
- **Introduced:** MKT-1D
- **Why deferred:** Daily JSONL files grow without bound. A real deployment will need a retention policy (e.g. archive after 90 days).
- **Resolves at:** when usage demands it.

### P-1D.5 — `mkt memory inspect` CLI
- **Introduced:** MKT-1D
- **Why deferred:** Useful for debugging (`mkt memory list demo-co audience`, `mkt memory check demo-co`) but no runtime exists yet.
- **Resolves at:** MKT-2A.

### P-1B.1 — Schema versioning / migration policy (SUPERSEDED by P-1D.2)
- This item is now tracked as **P-1D.2** above.

---

## From MKT-1E (workflow + agent + skill specs)

### P-1E.1 — Promote spec formats to versioned Pydantic contracts
- **Introduced:** MKT-1E
- **Why deferred:** MKT-1E intentionally documents `workflow-spec.v1`, `agent-spec.v1`, `skill-spec.v1` in prose and YAML, without binding them to Pydantic models. The right contract shape will emerge when the dispatcher tries to consume them.
- **Resolves at:** MKT-2A.
- **Sketch:** `core/contracts/specs/workflow.py`, `agent.py`, `skill.py` modeled on `envelope.v1` / `phase-gate.v1`.

### P-1E.2 — Spec linter
- **Introduced:** MKT-1E
- **Why deferred:** No tests exist for the specs themselves. Every `consumed_gate` should resolve to some `produced_gate`; every `agent_id` in a workflow should exist under `agents/`; every `skill_id` referenced by an agent should exist under `skills/`. Today these invariants are enforced by review, not code.
- **Resolves at:** MKT-2A.
- **Sketch:** `tools/lint_specs.py` walks `workflows/`, `agents/`, `skills/` and reports violations.

### P-1E.3 — Promote agents from `spec_only` to `implemented`
- **Introduced:** MKT-1E
- **Why deferred:** Every agent ships with `status: spec_only`. The dispatcher will refuse to spawn them until promoted.
- **Resolves at:** per-agent, block by block from MKT-2B onwards.

### P-1E.4 — Promote skills from `spec_only` to `implemented`
- **Introduced:** MKT-1E
- **Why deferred:** Skills are atomic capabilities; their implementation lives alongside the agent block that needs them first.
- **Resolves at:** per-skill, block by block.

### P-1E.5 — Approval Center implementation
- **Introduced:** MKT-1E
- **Why deferred:** The state machine is documented; the persisted state, the UI, and the human transition events are not.
- **Resolves at:** MKT-2B+ (likely with a small backend for approval entities + a temporary CLI before the Portal exists).

### P-1E.6 — n8n bridge (R3+ in `n8n-automation-roadmap.md`)
- **Introduced:** MKT-1E
- **Why deferred:** v1 only plans n8n workflows; nothing executes them. The trigger-only bridge is a separate, opt-in block.
- **Resolves at:** post-MKT-6.

### P-1E.7 — Portal (any phase)
- **Introduced:** MKT-1E
- **Why deferred:** UI choice is independent and orthogonal to the core. v1 has no Portal.
- **Resolves at:** dedicated block when the agency operationally needs it.

### P-1E.8 — Live analytics connectors
- **Introduced:** MKT-1E (carries forward from earlier blocks)
- **Why deferred:** All `MetricSource` values except `MANUAL` and `INTERNAL_REPORT` need real adapters.
- **Resolves at:** MKT-6A (EMAIL), MKT-6B (GA4 + SEARCH_SEO), post-MKT-6 (SOCIAL, PUBLIC_FOOTPRINT).

### P-1E.9 — CSV / JSON import for `INTERNAL_REPORT` Metrics
- **Introduced:** MKT-1E
- **Why deferred:** v1 accepts Metric entities written via Memory. A small import helper would make humans faster but is not blocking.
- **Resolves at:** MKT-2A (as part of the CLI surface).
