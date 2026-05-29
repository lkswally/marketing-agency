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
- **Status:** ⚠ partial — MKT-2A's dispatcher does NOT layer strict modes yet (mock envelopes are passed through `validate_envelope_strict` which is base schema only).
- **Resolves at:** MKT-2B (Claude Code spawn) onwards, per mode.

### P-1C.3 — `predicate_kind` evaluators
- **Introduced:** MKT-1C
- **Status:** ⚠ partial — MKT-2A implements only `envelope_present` (registered in `core/runtime/predicates.py`). Note: the dispatcher today consults the in-memory `held_gates` set directly; the registry is in place for the moment phases declare predicates beyond simple gate presence.
- **Resolves at:** per block. Remaining: `status_equals`, `claims_audit_present`, `no_unsafe_claims`, `memory_key_exists`, `artifact_exists`, `custom`.

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

### P-1D.5 — `mkt memory inspect` CLI  ✅ RESOLVED in MKT-2A
- **Introduced:** MKT-1D
- **Resolved at:** MKT-2A — `mkt memory inspect [--client SLUG]` available via the new `mkt` console script. Lists clients or, when a slug is given, prints per-kind entity counts plus audit-event count.
- **Notes:** `mkt memory list <kind>` and `mkt memory check` (referential integrity walker) are still pending; tracked as P-2A.1.

### P-1B.1 — Schema versioning / migration policy (SUPERSEDED by P-1D.2)
- This item is now tracked as **P-1D.2** above.

---

## From MKT-1E (workflow + agent + skill specs)

### P-1E.1 — Promote spec formats to versioned Pydantic contracts  ✅ partial in MKT-2A
- **Introduced:** MKT-1E
- **Status:** `workflow-spec.v1` promoted to Pydantic in `core/workflows/spec.py`. `agent-spec.v1` and `skill-spec.v1` remain frontmatter-only and are checked by the linter, not by a Pydantic model.
- **Notes on placement:** the workflow spec lives in `core/workflows/`, not `core/contracts/` (ADR 0006 D-6.1) — workflow specs are loaded artifacts, distinct from transport contracts.
- **Resolves at:** agent-spec / skill-spec promotion = MKT-2B when real agents land.

### P-1E.2 — Spec linter  ✅ RESOLVED in MKT-2A
- **Introduced:** MKT-1E
- **Resolved at:** MKT-2A — `core/workflows/linter.py` with `lint_workflow_spec`, `lint_agent_file`, `lint_skill_file`, and the orchestrator `lint_all`. Exposed via `mkt validate-specs` (CLI).
- **Notes:** real-repo lint is part of the test suite (`tests/workflows/test_spec_linter.py::test_lint_all_on_real_repo_has_no_errors`).

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
- **Status:** still deferred — MKT-2A's CLI does not include an import subcommand. The dispatcher proved the round-trip, but a user-friendly `mkt memory put` / `mkt memory import` is the actual blocker.
- **Resolves at:** later iteration of CLI (tracked alongside P-2A.1).

---

## From MKT-2A (minimal dispatcher + spec linter + CLI)

### P-2A.1 — Expand `mkt memory` CLI surface
- **Introduced:** MKT-2A
- **Why deferred:** v1 ships only `mkt memory inspect`. Useful additions: `mkt memory list <client> <kind>`, `mkt memory get <client> <kind> <id>`, `mkt memory check <client>` (referential integrity walker), `mkt memory put <client> <kind> <id> --from-file`, `mkt memory tail-audit <client>`.
- **Resolves at:** as needed for debugging and ops.

### P-2A.2 — Promote `agent-spec.v1` and `skill-spec.v1` to Pydantic contracts
- **Introduced:** MKT-2A
- **Why deferred:** MKT-2A's linter checks frontmatter shape but does not bind it to a Pydantic model. Promotion makes sense when the runtime starts loading agents to invoke them (not when it just lints their specs).
- **Resolves at:** MKT-2B.

### P-2A.3 — Claude Code subagent spawn backend
- **Introduced:** MKT-2A
- **Why deferred:** MKT-2A is mock-only by approved decision. The dispatcher already accepts an injectable agent (`MinimalDispatcher(memory, agent=...)`), so the swap is a single class.
- **Resolves at:** MKT-2B with its own approval.

### P-2A.4 — Parallel agents within a phase
- **Introduced:** MKT-2A
- **Why deferred:** W3.channel_mix lists three agents that conceptually run in parallel. v1 runs them sequentially. Correctness is unaffected for mocks; latency matters once real agents land.
- **Resolves at:** MKT-2B.

### P-2A.5 — Resume / retry policy
- **Introduced:** MKT-2A
- **Why deferred:** A failed run is final in v1. Future runs will need retry semantics (with backoff caps), and possibly resume-from-step semantics.
- **Resolves at:** MKT-2C.

### P-2A.6 — `WorkflowSpec` migration runner
- **Introduced:** MKT-2A
- **Why deferred:** Trivially folds into the broader migration runner (P-1D.2). Recorded here for traceability.
- **Resolves at:** with P-1D.2.

### P-2A.7 — Dispatcher should consult `predicates.evaluate` instead of `held_gates` only
- **Introduced:** MKT-2A
- **Why deferred:** The dispatcher today walks `gates_required_before` against an in-memory `held_gates` set. The predicate registry exists but is bypassed for the simple "gate held" case. Future predicate kinds (e.g. `no_unsafe_claims`) will need richer evaluation.
- **Resolves at:** MKT-3 / MKT-2B when the first non-`envelope_present` predicate is needed.
