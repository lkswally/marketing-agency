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

### P-2A.2 — Promote `agent-spec.v1` and `skill-spec.v1` to Pydantic contracts  ✅ RESOLVED in MKT-2B
- **Introduced:** MKT-2A
- **Resolved at:** MKT-2B — `core/agents/spec.py` and `core/skills/spec.py` ship Pydantic models. Loaders parse markdown frontmatter and validate. All 33 real specs validate.

### P-2A.3 — Claude Code subagent spawn backend
- **Introduced:** MKT-2A
- **Status:** ⚠ still scaffolding-only. MKT-2B added `core/runtime/backends/claude_code.py` (raises `NotImplementedError`) + the safety checklist in `docs/runtime/agent-backend-safety.md`. The runtime accepts a backend via `MinimalDispatcher(memory, agent_backend=...)`.
- **Resolves at:** dedicated block, only after every item in the safety checklist is satisfied AND with explicit user approval.

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

### P-2A.7 — Dispatcher should consult `predicates.evaluate` instead of `held_gates` only  ✅ RESOLVED in MKT-2B
- **Introduced:** MKT-2A
- **Resolved at:** MKT-2B — `core/runtime/predicates.evaluate_required_gate` is the dispatcher's single choke point. Today's policy delegates to `held_gates` (unchanged observable behavior), but future predicates (e.g. `no_unsafe_claims`) plug in at one place.

---

## From MKT-2B (agent/skill contracts + backend interface)

### P-2B.1 — `ClaudeCodeBackend` real implementation
- **Introduced:** MKT-2B
- **Why deferred:** Real LLM spawn with tools is high-risk and explicitly out of scope. Safety boundaries documented; no implementation until they are all in place.
- **Resolves at:** dedicated block with explicit approval AND completion of every item in `docs/runtime/agent-backend-safety.md` §3 promotion checklist.

### P-2B.2 — Parallel agents within a phase
- **Introduced:** MKT-2A (carried forward as P-2A.4) → still pending.
- **Why deferred:** Sequential is correct for mocks; parallelization matters once real agents land and W3.channel_mix runs three of them.
- **Resolves at:** same block as `ClaudeCodeBackend` or shortly after.

### P-2B.3 — Strict IO entry types for agent / skill specs
- **Introduced:** MKT-2B
- **Why deferred:** `AgentIOEntry` uses `extra="allow"` and `SkillSpec.inputs/outputs` accept `list[Any]` (dicts or strings). This is the trade-off taken to avoid rewriting 33 MKT-1E specs. A future block can introduce typed IO entries and migrate the specs.
- **Resolves at:** when the dispatcher needs to resolve typed upstream entities to pass into an agent.

### P-2B.4 — Audit event types for backend invocations
- **Introduced:** MKT-2B
- **Why deferred:** When `ClaudeCodeBackend` ships, it must emit `agent_spawned` / `agent_returned` / `agent_failed` (per safety doc §2.6). These are additive to `audit-trail.v1`.
- **Resolves at:** with `ClaudeCodeBackend` implementation.

### P-2B.5 — Runtime model resolution
- **Introduced:** MKT-2B
- **Why deferred:** `default_model` in specs is `opus | sonnet | haiku`. A real backend needs to resolve these to concrete model identifiers and override per invocation (e.g. retry with a stronger model). Out of scope today.
- **Resolves at:** with `ClaudeCodeBackend` implementation.

---

## From MKT-2B/2C era (MCP integration roadmap — documentation only)

> Full plan: `docs/mcp-roadmap.md`. This block introduced the roadmap; no
> code, no MCP connection, no credential setup happened. Every entry below
> resolves at its named MKT-MCP-N block, all of which are deferred until
> post MKT-2C and require explicit phase-by-phase approval before
> implementation.

### P-MCP.1 — MCP registry doc (MKT-MCP-1)
- **Introduced:** MKT-2B/2C (during MCP roadmap registration).
- **Why deferred:** Phase 1 of the MCP roadmap is itself documentation.
  Until MKT-2C closes, even adding a new doc carries scope risk.
- **Resolves at:** MKT-MCP-1 — produces `docs/mcp-registry.md` listing
  every MCP MKT will consider, with 7-filter eval status per entry.
- **Sketch:** registry doc + per-MCP permission template (already drafted
  in `mcp-roadmap.md` §"Permissions plan template").

### P-MCP.2 — Domain contracts for external data (MKT-MCP-2)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** Contracts only make sense once MKT-2C settles the
  current contract layer. Adding new Pydantic specs now risks churn.
- **Resolves at:** MKT-MCP-2 — adds `ExternalDataSource`, `MCPToolRef`,
  `ReadOnlyMetricQuery`, `MCPInsight` to `core/domain/`. Pure specs +
  tests; no connector code.
- **Sketch:** `ReadOnlyMetricQuery` includes a guard that rejects any
  query whose tool name matches write verbs (`create|update|delete|pause|
  resume|mutate|add|remove`).

### P-MCP.3 — GA4 read-only adapter (MKT-MCP-3)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** First real MCP integration. Requires P-MCP.1 +
  P-MCP.2 done, plus explicit approval per `mcp-roadmap.md` permissions
  template.
- **Resolves at:** MKT-MCP-3 — `integrations/ga4_adapter.py`. Scope
  `analytics.readonly`. Produces `Metric` entities with `source=GA4`,
  `is_estimate=false`, `confidence=1.0`. Fails open on missing credential.
- **Parallel scope:** Google Drive / Sheets read-only for report fetching
  in same block.

### P-MCP.4 — Google Ads read-only adapter (MKT-MCP-4)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** Highest-risk source (write surface includes campaign
  pause / budget mutation). Requires P-MCP.3 to establish the adapter
  pattern first.
- **Resolves at:** MKT-MCP-4 — `integrations/google_ads_adapter.py`.
  Strict no-mutate gate: rejects tool names matching write verbs even if
  the underlying MCP exposes them. New enum value `GOOGLE_ADS` in
  `Metric.source` (tracked as a separate domain bump).

### P-MCP.5 — Search Console / SEO source (MKT-MCP-5)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** Requires MCP adapter pattern from P-MCP.3.
- **Resolves at:** MKT-MCP-5 — `integrations/search_console_adapter.py`.
  Scope `webmasters.readonly`. Reads queries, impressions, CTR, position.
  Produces `Metric` with `source=SEARCH_SEO`.

### P-MCP.6 — Automated reporting agent goes live (MKT-MCP-6)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** `analytics-agent` is specced in MKT-1E but has no
  real Metrics to consume until MCP-3/4/5 land.
- **Resolves at:** MKT-MCP-6 — new skill `mcp-report-generator` fans out
  read queries to every active `ExternalDataSource` and produces a
  unified `MCPInsight`. Output: versioned `report.v1` memory entity. No
  actions yet.

### P-MCP.7 — Actionable recommendations + Gmail read-only (MKT-MCP-7)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** `optimizer-agent` needs `MCPInsight`s from MCP-6 to
  produce meaningful recommendations.
- **Resolves at:** MKT-MCP-7 — recommendations recorded as
  `recommendation.v1` entities, NOT executed. Gmail MCP integration
  read-only enters here (read inbox stats + existing drafts; no draft
  creation, no send).

### P-MCP.8 — Approved write actions via n8n / action layer (MKT-MCP-8)
- **Introduced:** MKT-2B/2C.
- **Why deferred:** First write surface. Requires every prior MCP phase
  to be stable AND `approval-center` (already specced in
  `docs/approval-center.md`) to be live.
- **Resolves at:** MKT-MCP-8 — bridge between MKT recommendations and
  n8n workflows (per `n8n-automation-roadmap.md` D-5.4). Per-action
  human approval mandatory. Gmail draft creation, ad budget changes,
  keyword additions all go through this gate.
- **Sketch:** new contract `ApprovedActionEnvelope` linking
  `recommendation.v1` + approval signature + n8n workflow id.

### P-MCP.9 — ADR for MCP integration architecture  ✅ partial in MKT-2C
- **Introduced:** MKT-2B/2C.
- **Status:** Foundational ADR landed in MKT-2C as `docs/decisions/0008-mkt-2c-external-data-mcp-roadmap.md` (D-8.1..D-8.12 covering posture, mapping, phasing, policy, credentials, n8n execution role, audit reservations). The implementation-time ADR (where adapters live, caching policy, etc.) is still scheduled for the block that ships the first adapter.
- **Resolves at:** with MKT-MCP-3 (implementation ADR `D-MCP.1`).

---

## From MKT-2C (external data & MCP roadmap)

### P-2C.1 — Promote conceptual contracts to Pydantic
- **Introduced:** MKT-2C
- **Why deferred:** `ExternalDataSource`, `MCPToolRef`, `ReadOnlyMetricQuery`, `ExternalInsight`, `DataPermissionPolicy`, `MarketingRecommendation`, `ProposedAction` live as YAML sketches in `external-data-sources.md` and `permissions-policy.md`. Promotion happens when the first adapter consumes them (same pattern as MKT-1E specs).
- **Resolves at:** MKT-MCP-2 (per `mcp-roadmap.md` phasing).

### P-2C.2 — Per-source R3 implementations (read-only programmatic)
- **Introduced:** MKT-2C
- **Status:** seven roadmap docs in place (`mcp-roadmap.md`, `google-analytics-roadmap.md`, `google-ads-roadmap.md`, `search-console-roadmap.md`, `external-data-sources.md`, `permissions-policy.md`, `n8n-execution-roadmap.md`). No adapter exists.
- **Resolves at:** per-source, MKT-MCP-3 (GA4 + Drive) → MKT-MCP-4 (Ads) → MKT-MCP-5 (GSC) → MKT-MCP-7 (Gmail).

### P-2C.3 — Per-source R4 implementations (write with approval)
- **Introduced:** MKT-2C
- **Why deferred:** Each write phase needs its own ADR + the safety checklist from `permissions-policy.md` §5.2. Google Ads R4 additionally requires double-approval policy and per-call caps (per ADR 0008 D-8.7).
- **Resolves at:** dedicated ADR per (source, write tool), only after the safety checklist is satisfied AND with explicit approval.

### P-2C.4 — n8n trigger contract + webhook signing
- **Introduced:** MKT-2C
- **Why deferred:** Sketched in `n8n-execution-roadmap.md` §2; implementation (signing, ack listener, registry validation) belongs to MKT-MCP-8.
- **Resolves at:** MKT-MCP-8.

### P-2C.5 — Credentials adapter
- **Introduced:** MKT-2C
- **Why deferred:** Specs reference credentials by name only (`env(GA4_SERVICE_ACCOUNT_JSON)`). The resolver — including per-client vs agency-wide policy — only matters when the first real adapter lands.
- **Resolves at:** MKT-MCP-3.

### P-2C.6 — `ProposedAction` entity + state machine
- **Introduced:** MKT-2C
- **Why deferred:** Documented in `external-data-sources.md` §3.7 as a YAML sketch. Implementation as a `core.domain` entity + Approval-Center integration is the scope of the block that opens the first R4 phase.
- **Resolves at:** with the first R4 source.

### P-2C.7 — Audit event types for external integrations
- **Introduced:** MKT-2C
- **Why deferred:** Eleven event types reserved across `permissions-policy.md` §6 and `n8n-execution-roadmap.md` §6 (`external_fetch`, `external_fetch_failed`, `proposed_action_created/approved/executed/failed`, `external_action_rejected`, `n8n_trigger_dispatched/failed`, `n8n_action_completed/failed`). All additive to `audit-trail.v1`.
- **Resolves at:** declared per integration block as the events become emitted.

### P-2C.8 — Decide `MetricSource` enum strategy for Google Ads / YouTube
- **Introduced:** MKT-2C
- **Why deferred:** Reuse `social` with `dimensions.provider=google_ads` vs add first-class enum values (`google_ads`, `youtube`). Reversible at the cost of a domain-model bump.
- **Resolves at:** with MKT-MCP-4 (Google Ads adapter block).

---

## From MKT-3A (campaign strategy engine)

### P-3A.1 — LLM-backed strategy generators
- **Introduced:** MKT-3A
- **Why deferred:** MKT-3A's generators are template-driven on purpose. Real LLM generation is more expressive but requires the safety boundaries in `docs/runtime/agent-backend-safety.md` to be in place.
- **Resolves at:** dedicated block, after `ClaudeCodeBackend` safety checklist is satisfied AND with explicit user approval. The deterministic generators in `core/strategy/templates.py` stay as the regression baseline.

### P-3A.2 — Promote MKT-1E agent specs from `spec_only` to `implemented`
- **Introduced:** MKT-1E (P-1E.3) → reaffirmed at MKT-3A.
- **Status:** still `spec_only`. W7 references agents by `agent_id` for documentation, but `TemplatedStrategyBackend` does the actual work without invoking the agents in the spawn sense.
- **Resolves at:** with LLM-backed generators (P-3A.1).

### P-3A.3 — Claim audit enforcement on the strategy report  ✅ RESOLVED in MKT-3B
- **Introduced:** MKT-3A
- **Resolved at:** MKT-3B — `core/approval/` ships `ClaimAuditor` + `ApprovalPack` (`approval-pack.v1`). 22 default rules covering 12 risk categories. `blocks_publish` policy in place for future publishers to honor.

### P-3A.4 — Approval Center halt-and-wait
- **Introduced:** MKT-3A (carries P-1E.5).
- **Status:** ⚠ partial — MKT-3B ships the data the Approval Center will consume (`ApprovalPack` with state machine). The dispatcher still does not halt mid-workflow at `g_approval_packaged`. The formal `Approval` entity from `docs/approval-center.md` remains unimplemented.
- **Resolves at:** dedicated Approval Center implementation block (post-MKT-3B).

### P-3A.5 — Versioned strategies per client
- **Introduced:** MKT-3A
- **Why deferred:** v1 uses singleton id `"current"` — a re-run overwrites the prior strategy. Versioning (history, comparison, rollback) is its own block.
- **Resolves at:** when an operational case demands it.

### P-3A.6 — Real image generation
- **Introduced:** MKT-3A
- **Why deferred:** `CreativeBriefPack` produces prompts; no image API is called. Image generation has its own cost / IP / hosting trade-offs.
- **Resolves at:** post-MCP / post-Replicate integration block.

### P-3A.7 — Parallel phase execution
- **Introduced:** MKT-3A (carries P-2A.4 / P-2B.2).
- **Why deferred:** Latency is fine for deterministic generation. Real LLM blocks land in seconds-to-minutes territory and would benefit from parallelism.
- **Resolves at:** with LLM-backed backend.

### P-3A.8 — `mkt strategy diff` / preview / publish CLI affordances
- **Introduced:** MKT-3A
- **Why deferred:** v1 ships `mkt run-strategy` and nothing else strategy-specific. Diff / preview / publish are useful but not blocking.
- **Resolves at:** as operational need appears.

### P-3A.9 — Direct integration with Approval Center entities
- **Introduced:** MKT-3A
- **Status:** ⚠ partial — MKT-3B's `ApprovalPack` is the input artifact a real Approval Center will consume. The `Approval` entity from `docs/approval-center.md` (with `PROPOSED → IN_REVIEW → APPROVED | REJECTED | NEEDS_REVISION` state machine) still does not exist as a domain entity.
- **Resolves at:** Approval Center implementation block.

---

## From MKT-3B (claim audit + approval pack)

### P-3B.1 — LLM-backed claim detection
- **Introduced:** MKT-3B
- **Why deferred:** Regex rules catch obvious risky language. An LLM-augmented detector would catch paraphrases and tone-level risks the rules miss. Requires the safety boundaries from `docs/runtime/agent-backend-safety.md`.
- **Resolves at:** dedicated block, post-ClaudeCodeBackend approval. The deterministic rules in `core/approval/claim_auditor.py` stay as the regression baseline.

### P-3B.2 — Workflow-level halt at `g_approval_packaged`
- **Introduced:** MKT-3B
- **Why deferred:** The dispatcher (MKT-2A) does not pause mid-run. The pack records state and `blocks_publish`, but the workflow still runs to completion.
- **Resolves at:** with the Approval Center implementation block.

### P-3B.3 — Promote approval audit events to first-class `audit-trail.v2` types
- **Introduced:** MKT-3B
- **Why deferred:** Today the pack lifecycle events are emitted as `event_type=note` with a `payload.approval_pack.action` discriminator. Promotion to first-class types (`approval_pack_created`, `approval_pack_approved`, etc.) is additive but premature without a bundle of external integrations also needing new types.
- **Resolves at:** with the first external publisher block (likely MKT-MCP-8) — bundle all reserved event types into a single `audit-trail.v2` bump.

### P-3B.4 — Per-client custom rule sets loaded from disk
- **Introduced:** MKT-3B
- **Why deferred:** `ClaimAuditor(rules=...)` already accepts a custom rule list programmatically. A YAML/JSON loader for `data/clients/<slug>/approval/rules.yaml` is just plumbing.
- **Resolves at:** when a client needs override rules.

### P-3B.5 — `mkt approve` / `mkt reject` CLI subcommands
- **Introduced:** MKT-3B
- **Why deferred:** The Python API (`ApprovalPackBuilder.approve(...)` / `.reject(...)`) is the source of truth. CLI subcommands are convenience for ops scripts.
- **Resolves at:** when the operational case demands it.

### P-3B.6 — Versioned packs (history / diff)
- **Introduced:** MKT-3B
- **Why deferred:** v1 uses singleton id `"current"`. Re-auditing overwrites. Versioned history is useful for "what changed since my last review?" but not blocking v1.
- **Resolves at:** dedicated block when reviewer workflow demands it.

### P-3B.7 — External publishers honoring `blocks_publish`
- **Introduced:** MKT-3B
- **Why deferred:** The flag is set; no publisher exists in MKT-3B to consult it.
- **Resolves at:** MKT-MCP-8 (n8n trigger), per-source publish blocks.

### P-3B.8 — Source-aware evidence linking
- **Introduced:** MKT-3B
- **Why deferred:** Detections support `evidence_refs: list[str]` but the auditor does not populate them. Linking detections to `Evidence` entities (MKT-1B) requires a knowledge-base lookup or per-client evidence registry.
- **Resolves at:** continuation block when a real evidence catalogue exists.

### P-3B.9 — Image-content audit
- **Introduced:** MKT-3B
- **Why deferred:** The auditor checks text only. When image generation lands, images will need their own audit (brand safety, generated text, depictions).
- **Resolves at:** post image-gen block.

---

## From MKT-3C (creative factory pack)

### P-3C.1 — LLM-backed copy generation
- **Introduced:** MKT-3C
- **Why deferred:** Variants are deterministic template rotations. LLM-backed generation would produce richer, more contextual A/B variants but requires the safety boundaries in `docs/runtime/agent-backend-safety.md`.
- **Resolves at:** dedicated block, post Claude Code safety + explicit approval. The deterministic templates in `core/creative/factory.py` remain the regression baseline.

### P-3C.2 — Real image generation from prompts
- **Introduced:** MKT-3C
- **Why deferred:** `ImagePromptAsset` produces ready-to-paste prompts; no image API is called. Image generation has its own cost / IP / hosting trade-offs.
- **Resolves at:** post-MCP / Replicate integration block.

### P-3C.3 — Workflow-level integration with W7
- **Introduced:** MKT-3C
- **Why deferred:** The creative pack is built post-hoc by a separate CLI command, not as a phase of W7 (the strategy workflow). Wiring it in would couple two distinct concerns.
- **Resolves at:** when the operational pipeline (`strategy → audit → build-creatives`) needs to live as a single workflow run.

### P-3C.4 — Versioned packs (history / diff)
- **Introduced:** MKT-3C
- **Why deferred:** v1 uses singleton id `"current"`. Re-running overwrites. Versioned history would be useful for comparing variants over time.
- **Resolves at:** when an operational case demands it.

### P-3C.5 — Per-channel format adaptation beyond default flyers
- **Introduced:** MKT-3C
- **Why deferred:** v1 produces three flyer formats (1:1, 4:5, 9:16). Adapting copy to Reels-as-Story vs LinkedIn carousel vs IG static would need a per-format template registry.
- **Resolves at:** continuation block when channel-specific outputs are required.

### P-3C.6 — Outcome tracking (A vs B winner)
- **Introduced:** MKT-3C
- **Why deferred:** A/B variants ship with stable ids and tagged angles/styles. There is no analytics layer yet to attribute results.
- **Resolves at:** when a publishing surface (MKT-MCP-8) and a metrics adapter (MKT-MCP-3) both exist.

### P-3C.7 — ICS / Google Calendar export
- **Introduced:** MKT-3C
- **Why deferred:** The pack carries dates per asset. Exporting as an `.ics` file or pushing to a Google Calendar is integration plumbing, not a missing capability.
- **Resolves at:** as needed.

### P-3C.8 — `mkt creative diff` / preview / publish CLI affordances
- **Introduced:** MKT-3C
- **Why deferred:** v1 ships `mkt build-creatives` and nothing else creative-specific.
- **Resolves at:** as operational need appears.

### P-3C.9 — `PublicationLog` entity (separate from pack state)
- **Introduced:** MKT-3C
- **Why deferred:** ADR 0011 D-11.12 explicitly decided that the pack does NOT carry a `PUBLISHED` state. A future publisher writes a separate log. The log's shape is not yet defined.
- **Resolves at:** with the first publisher block (MKT-MCP-8 or per-source adapter).

### P-3C.10 — Promote `creative_pack` audit events to `audit-trail.v2`
- **Introduced:** MKT-3C
- **Why deferred:** Events are wrapped in `note` with `payload.creative_pack.action`. Same trade-off as MKT-3B's approval events — wait for a batch promotion to `audit-trail.v2`.
- **Resolves at:** bundled with the next audit-trail bump.

---

## From MKT-3D (visual direction & image prompt pack)

### P-3D.1 — LLM-backed visual prompt generation
- **Introduced:** MKT-3D
- **Why deferred:** Variants are template-driven (A: editorial, B: bold typographic). LLM-backed generation would produce richer, more contextual prompts but requires the safety boundaries in `docs/runtime/agent-backend-safety.md`.
- **Resolves at:** dedicated block, post Claude Code safety + explicit approval. The deterministic generators in `core/visual/prompt_factory.py` remain the regression baseline.

### P-3D.2 — Real image generation from the prompts
- **Introduced:** MKT-3D
- **Why deferred:** The Visual Direction Pack is 100% text. Real image generation introduces cost, IP, hosting and safety considerations distinct from prompt generation.
- **Resolves at:** post-MCP / Replicate / image-gen integration block. Will land as a separate adapter (`integrations/image_*.py`) consuming `VisualPromptVariant.full_prompt_text` + `negative_prompt`.

### P-3D.3 — Three or more prompt variants per piece type
- **Introduced:** MKT-3D
- **Why deferred:** v1 ships two variants per piece (A: editorial, B: bold). Three would multiply combinations without proportional analytical benefit at this stage.
- **Resolves at:** continuation block when A/B outcomes reveal which axes matter.

### P-3D.4 — Per-client custom visual style overrides
- **Introduced:** MKT-3D
- **Why deferred:** Style guide is template-driven from the report. A per-client `data/clients/<slug>/visual/style.yaml` override would let agencies pin brand-specific palettes / typography.
- **Resolves at:** when a client needs override-by-default behavior.

### P-3D.5 — Import `Brand.visual_rules` from MKT-1B into the style guide
- **Introduced:** MKT-3D
- **Why deferred:** `Brand.visual_rules` exists as a dict in the domain model but the strategy engine does not populate it from the input brief yet. When it does, the visual factory should consume it instead of defaulting.
- **Resolves at:** when brand visual rules are actively populated.

### P-3D.6 — Figma frame export
- **Introduced:** MKT-3D
- **Why deferred:** The pack carries enough information (dimensions, safe zones, hex palette) to scaffold Figma frames programmatically via their API. Out of scope for v1.
- **Resolves at:** as needed.

### P-3D.7 — Outcome tracking (A vs B winner) for visual prompts
- **Introduced:** MKT-3D
- **Why deferred:** Variants ship with stable ids (A, B) and tagged styles. Attribution requires a publishing surface and an analytics adapter.
- **Resolves at:** when MKT-MCP-8 (publish) and MKT-MCP-3 (analytics) both exist.

### P-3D.8 — Image-content audit
- **Introduced:** MKT-3D (paired with P-3B.9).
- **Why deferred:** The claim auditor (MKT-3B) is text-only. Once images are generated, they need their own audit pass (brand safety, generated text on image, depictions, copyright).
- **Resolves at:** post image-gen block.

### P-3D.9 — `mkt visual diff` / preview CLI affordances
- **Introduced:** MKT-3D
- **Why deferred:** v1 ships `mkt build-visuals` and nothing else visual-specific.
- **Resolves at:** as operational need appears.

### P-3D.10 — Promote `visual_pack` audit events to `audit-trail.v2`
- **Introduced:** MKT-3D
- **Why deferred:** Events are wrapped in `note` with `payload.visual_pack.action`. Same trade-off as MKT-3B/3C. Will batch with other promotions.
- **Resolves at:** bundled with the next audit-trail bump.

---

## From MKT-3E (client brief intake pack)

### P-3E.1 — Web form / landing page for intake
- **Introduced:** MKT-3E
- **Why deferred:** Explicitly out of scope by user direction. v1 ships CLI + JSON only.
- **Resolves at:** dedicated landing / portal block.

### P-3E.2 — LLM-assisted intake completion
- **Introduced:** MKT-3E
- **Why deferred:** The validator surfaces missing fields. An LLM-backed assistant could *suggest* values based on similar past intakes. Requires the safety boundaries from `docs/runtime/agent-backend-safety.md`.
- **Resolves at:** post-Claude Code safety + explicit approval.

### P-3E.3 — Interactive `mkt intake --wizard` CLI mode
- **Introduced:** MKT-3E
- **Why deferred:** CLI is one-shot (`--file`). A wizard would walk the user through prompts and emit the JSON.
- **Resolves at:** as operational case demands.

### P-3E.4 — Import adapters (Notion / Google Forms / Typeform)
- **Introduced:** MKT-3E
- **Why deferred:** v1 only reads local JSON. External-source adapters live in `integrations/` and follow the same R1-R4 phasing as the MCP roadmap.
- **Resolves at:** per-source integration blocks.

### P-3E.5 — Multi-language intake support
- **Introduced:** MKT-3E
- **Why deferred:** The demo mixes Spanish and English freely. Real multi-language UX would need locale-aware validator messages and templates.
- **Resolves at:** continuation block when a non-Spanish client demands it.

### P-3E.6 — Versioned intake history (diff between two intake files)
- **Introduced:** MKT-3E
- **Why deferred:** v1 uses singleton id `"current"`. Re-running overwrites.
- **Resolves at:** when iterative editing of intakes becomes a real ops case.

### P-3E.7 — Intake-side image attachments (logo, reference visuals)
- **Introduced:** MKT-3E
- **Why deferred:** Intake is text-only in v1. Logos and reference images would need attachment handling.
- **Resolves at:** post-image-gen block.

### P-3E.8 — `mkt intake diff` for comparing two intake files
- **Introduced:** MKT-3E
- **Why deferred:** Useful as an ops affordance, not blocking.
- **Resolves at:** as needed.

### P-3E.9 — Promote `intake` audit events to `audit-trail.v2`
- **Introduced:** MKT-3E
- **Why deferred:** Events are wrapped in `note` with `payload.intake.action`. Same trade-off as MKT-3B/3C/3D. Will batch.
- **Resolves at:** bundled with the next audit-trail bump.

### P-3E.10 — Auto-chain `intake → run-strategy --audit` as a single command
- **Introduced:** MKT-3E
- **Why deferred:** ADR 0013 D-13.7 explicitly chose NOT to auto-chain so warnings stay visible. An `--auto-run` flag is feasible but defaults must stay off.
- **Resolves at:** when operational case demands it.

---

## From MKT-3F (campaign pipeline orchestrator)

### P-3F.1 — Per-run archive of `campaign-final-summary.{md,json}`
- **Introduced:** MKT-3F
- **Why deferred:** Re-runs overwrite the latest summary. Historical runs are visible only via the audit trail. Adding `outputs/<slug>/runs/<run_id>/` would duplicate disk usage; postponed until an operator actually needs side-by-side diffing.
- **Resolves at:** when an operations review requires comparing two runs.
- **Sketch:** `--archive` flag → write a `runs/<run_id>/` snapshot in addition to the canonical `outputs/<slug>/` files.

### P-3F.2 — Parallelize creative + visual after approval
- **Introduced:** MKT-3F
- **Why deferred:** Sequential is fine at current volumes (deterministic templates, sub-second per stage). The cut is natural (both depend on approval, neither on each other) but YAGNI.
- **Resolves at:** when batch processing >50 campaigns/run becomes a real workload.
- **Sketch:** wrap stages 4+5 in `concurrent.futures.ThreadPoolExecutor(max_workers=2)`; preserve ordering in `summary.stages`.

### P-3F.3 — Pipeline run audit events as first-class `audit-trail.v2`
- **Introduced:** MKT-3F
- **Why deferred:** Events are wrapped in `note` with `payload.campaign_pipeline.{stage, action}`, same trade-off taken in MKT-3B/3C/3D/3E. Will batch with the next contract bump.
- **Resolves at:** bundled with the next audit-trail revision.

### P-3F.4 — `mkt campaign show <run_id>` to re-render a past run
- **Introduced:** MKT-3F
- **Why deferred:** Useful once P-3F.1 lands; without per-run archives there is nothing to re-render.
- **Resolves at:** after P-3F.1.

### P-3F.5 — Multi-tenant concurrency guard for the same `client_slug`
- **Introduced:** MKT-3F
- **Why deferred:** The orchestrator assumes single-writer per slug. Running two `mkt run-campaign` for the same slug concurrently is a user error; no lockfile yet.
- **Resolves at:** if/when the system gets a daemon or queue mode.
- **Sketch:** advisory file lock at `data/clients/<slug>/.lock` with PID + timestamp; refuse to run if held.

### P-3F.6 — Stage retries with idempotency
- **Introduced:** MKT-3F
- **Why deferred:** Every stage is deterministic and runs in-process; retries are not needed today. Becomes relevant only once a stage calls a real external service (LLM, image gen, n8n).
- **Resolves at:** at the same time the first external-call stage lands.

### P-3F.7 — Surface intake warnings inline in `campaign-final-summary.md`
- **Introduced:** MKT-3F
- **Why deferred:** The summary lists counts (`critical/warning/info`) but not the actual messages. The full list lives in `intake-summary.md`. Adding it inline would balloon the summary; cross-link suffices for now.
- **Resolves at:** when operator feedback says the cross-link is not enough.

### P-3F.8 — `--archive-on-block` to keep blocked-run outputs separately
- **Introduced:** MKT-3F
- **Why deferred:** Blocked runs currently overwrite the canonical outputs with the SKIPPED state. An operator who wants to keep a blocked snapshot for diff against a later clean run would need a flag.
- **Resolves at:** when P-3F.1 lands (this is a specialization).

---

## From MKT-4A (controlled Claude strategy backend)

### P-4A.1 — Real `ClaudeInvoker` implementation (MKT-4B)
- **Introduced:** MKT-4A
- **Why deferred:** MKT-4A explicitly ships **infrastructure only**. No real LLM invocation, no SDK, no subprocess, no network — by spec. The cleanest single-file extension point (`ClaudeInvoker.complete(...)`) is in place and the entire fallback / audit / summary plumbing is exercised by `RefusingClaudeInvoker` and `ScriptedClaudeInvoker`.
- **Resolves at:** **MKT-4B**.
- **Sketch:** add `core/strategy/backends/invokers/anthropic_sdk.py` with `AnthropicSDKInvoker(api_key=..., model=...)`. Wire env-var resolution and credential redaction. Keep the same `ClaudeInvoker` interface. No code changes elsewhere.

### P-4A.2 — Per-method retry / backoff in the Claude backend
- **Introduced:** MKT-4A
- **Why deferred:** MKT-4A treats every invoker failure as a single-shot fallback. A real invoker will need retries (transient 5xx, rate-limit, timeout) before declaring failure.
- **Resolves at:** MKT-4B alongside the real invoker.
- **Sketch:** add `max_retries: int = 2` and exponential backoff to `_invoke_or_fallback`. Each retry attempt is NOT a fallback event; only the final failure counts.

### P-4A.3 — Streaming / partial-output support
- **Introduced:** MKT-4A
- **Why deferred:** `ClaudeInvoker.complete(...)` returns a full string. Streaming would change the interface to yield chunks and would need a JSON-streaming parser. Out of scope.
- **Resolves at:** when an actual UX requires it (e.g. a dashboard live view). Not before MKT-5.
- **Sketch:** `ClaudeInvoker.stream(...) -> Iterator[str]` alternate method; the backend buffers and validates at the end.

### P-4A.4 — Tool use / multi-turn conversations from the invoker
- **Introduced:** MKT-4A
- **Why deferred:** Single-shot prompts are sufficient for the six creative methods. Tool use opens an entirely new safety surface (the safety policy in `agent-backend-safety.md` would need to be extended).
- **Resolves at:** post-MKT-5, with its own ADR and threat model.

### P-4A.5 — Prompt versioning + per-tenant prompt overrides
- **Introduced:** MKT-4A
- **Why deferred:** Prompts live in `backends/prompts.py` as plain strings. A future block may want versioned, JSON-schema-driven prompts and a per-tenant override mechanism so a specific client gets a custom tone of voice.
- **Resolves at:** when client-specific prompt tuning becomes a real ask.
- **Sketch:** `prompts/v1/*.txt` directory + a `PromptLoader(tenant_overrides_root=...)`.

### P-4A.6 — Cost / token tracking in the Claude backend
- **Introduced:** MKT-4A
- **Why deferred:** No real invoker → no real tokens. Adding counters in MKT-4A would be theatre.
- **Resolves at:** MKT-4B with the real invoker.
- **Sketch:** invoker returns `CompletionResult(text, input_tokens, output_tokens, model, cost_usd)` instead of `str`; the backend records aggregates per run in the summary.

### P-4A.7 — Non-zero CLI exit on fallback (opt-in)
- **Introduced:** MKT-4A
- **Why deferred:** By explicit spec ("El pipeline puede terminar con exit 0 si el fallback completa correctamente"). Some operators (CI) might want a non-zero exit. Optional flag like `--fail-on-fallback` could be added.
- **Resolves at:** if a real CI workflow needs it.
- **Sketch:** add `--fail-on-fallback` to `run-campaign`; when set and `backend_fallback_count > 0`, exit with a new code (e.g. 5).

### P-4A.8 — Promote `strategy_backend_fallback` to `audit-trail.v2`
- **Introduced:** MKT-4A
- **Why deferred:** Events are wrapped in the generic `note` event type with `payload.campaign_pipeline.action == "strategy_backend_fallback"`. Same trade-off taken in MKT-3B/3C/3D/3E/3F. Will batch with the next audit-trail bump.
- **Resolves at:** bundled with the next `audit-trail` contract revision.

### P-4A.9 — Hot-swap the fallback target
- **Introduced:** MKT-4A
- **Why deferred:** `ClaudeStrategyBackend` accepts a `fallback: StrategyBackend | None` constructor kwarg but in practice everyone uses the default (`TemplatedStrategyBackend`). A future block might want to chain backends (e.g. Claude → local-LLM → templated).
- **Resolves at:** when a second non-templated backend exists.

### P-4A.10 — Move workflows YAML comment off the legacy class name
- **Introduced:** MKT-4A
- **Why deferred:** `workflows/W7_campaign_strategy_engine.yaml` mentions `core.strategy.TemplatedStrategyBackend` in a comment. The class was renamed to `W7TemplatedAgentBackend` with an alias preserved for backward compat. Comment is stale but harmless.
- **Resolves at:** next time the YAML is edited.

---

## From MKT-4B (anthropic sdk invoker)

### P-4B.1 — Retry policy for transient errors
- **Introduced:** MKT-4B
- **Why deferred:** ADR 0016 D-16.4 explicitly chose one attempt per method. Adding retries needs a real policy (exponential vs linear, jitter, per-method budget, total run budget). No operational signal yet to choose.
- **Resolves at:** when production runs surface `RateLimitError` recurrently.
- **Sketch:** opt-in `retry: RetryPolicy | None = None` on `AnthropicSDKInvoker`. Cap at 3 attempts. Backoff with jitter. Record each attempt as a separate `ClaudeInvocationRecord` so the timeline stays auditable.

### P-4B.2 — Streaming responses
- **Introduced:** MKT-4B
- **Why deferred:** The pipeline consumes the full string before parsing; streaming buys nothing on the strategy run path. Could matter for a future interactive CLI.
- **Resolves at:** when an interactive `mkt chat` exists.

### P-4B.3 — Per-tenant cost tracking + budget guard
- **Introduced:** MKT-4B
- **Why deferred:** `ClaudeInvocationRecord` already carries `input_tokens` / `output_tokens` per call; an aggregator + dashboard is a small project on top. Out of scope here.
- **Resolves at:** when a multi-tenant deployment exists.
- **Sketch:** `mkt costs --client <slug> [--since <date>]` walks the audit trail and aggregates tokens × $ per model. Budget guard: per-client monthly cap in `data/clients/<slug>/budget.json`; orchestrator refuses to wire SDK invoker once the cap is hit.

### P-4B.4 — Multi-model cascade (Sonnet → Haiku → templated)
- **Introduced:** MKT-4B
- **Why deferred:** Today only one model is configured; cascade is YAGNI for the immediate use case but cheap to add once cost matters.
- **Resolves at:** with P-4B.3.

### P-4B.5 — Prompt caching via `cache_control`
- **Introduced:** MKT-4B
- **Why deferred:** Per-tenant prompts include the brief which changes per client; cache hit rate would be near zero. Once a stable system prompt + few-shot scaffold ships, prompt caching the static prefix saves money.
- **Resolves at:** when system prompt + scaffold cross 1024 tokens of stable content.

### P-4B.6 — Async invoker
- **Introduced:** MKT-4B
- **Why deferred:** The orchestrator is single-threaded and the 6 creative methods have data dependencies that mostly serialise them anyway. An async invoker would only help if parallelism is added at the orchestrator level (which is P-3F.2).
- **Resolves at:** with P-3F.2.

### P-4B.7 — Integration test suite against the real API
- **Introduced:** MKT-4B
- **Why deferred:** Tests are 100% mocked. A separate `pytest -m integration` job that runs against the real API with a low-budget sandbox key would catch SDK drift early.
- **Resolves at:** when a sandbox API key is provisioned for CI.

### P-4B.8 — Claude Code subprocess as a SECOND invoker
- **Introduced:** MKT-4B
- **Why deferred:** Rejected as the primary invoker (analysis in MKT-4B handoff: traceability + production fit). Could still be useful as a SECOND invoker for dev environments where the operator wants to use their Claude Pro/Max subscription instead of an API key.
- **Resolves at:** if demand exists.

### P-4B.9 — Surface invocation count in the JSON CLI summary
- **Introduced:** MKT-4B
- **Why deferred:** The CLI stdout JSON has `stage_counts`, `backend_fallback_count` and so on but does NOT expose `claude_invocations` directly (only via the on-disk `campaign-final-summary.json`). For CI consumers that just diff exit code + counts, adding `claude_invocation_count` and `claude_invocation_ok_count` to the CLI payload would be convenient.
- **Resolves at:** when an external consumer asks for it.

### P-4B.10 — Pin model id behind a single source of truth
- **Introduced:** MKT-4B
- **Why deferred:** `DEFAULT_ANTHROPIC_MODEL` is a module constant. Anthropic ships new Sonnet/Opus/Haiku versions periodically. A `models.toml` (or env-overridable registry) would centralise the version pin and make rollover a one-line change.
- **Resolves at:** at the next model upgrade.

---

## From MKT-4C (real campaign quality pass)

Detected by running the pipeline on a real intake (`examples/intake/marketing-agency-os.json`) and reading the generated outputs. Full evaluation: `docs/qa/mkt-4c-real-campaign-quality-pass.md`.

### P-4C.1 — Templates ignore `brand_tone`
- **Introduced:** MKT-4C
- **Why deferred:** Out of scope for an evaluation block; the right fix is a tone-aware adjective/verb selector that maps `brand_tone` entries to lexical choices in `core/strategy/templates.py`. Bigger than a one-liner.
- **Resolves at:** MKT-4D (template content quality pass).
- **Sketch:** small `_tone_lexicon(brand_tone) -> dict[str, list[str]]` returning preferred adjectives, verbs and connectors per tone family. Inject into headline / big_idea / channel rationale templates.

### P-4C.2 — Templates ignore `preferred_words`
- **Introduced:** MKT-4C
- **Why deferred:** Same as P-4C.1 — needs an injection point in headline, big_idea and at least one copy per channel.
- **Resolves at:** MKT-4D.
- **Sketch:** in `generate_value_proposition` + `generate_campaign_strategy` + `generate_social_post_drafts`, prefer at least 2 words from `brief.brand.lexicon_do` when synthesizing strings.

### P-4C.3 — Placeholder phrase "X: Diseñado específicamente para Y" reused 6× (CRITICAL)
- **Introduced:** MKT-4C
- **Why deferred:** This is the single biggest source of perceived genericness in the output. Shows up as headline, big_idea, value prop, carrusel copy, social post body and reels voiceover. Each surface needs its own template; today they all derive from one `_format_value_prop_seed()` call.
- **Resolves at:** MKT-4D.
- **Sketch:** distinct seed phrases per surface, derived from different intake fields (industry-specific pain, audience-specific desired outcome, competitor differential).

### P-4C.4 — Keyword cluster extractor produces junk clusters (`diseado`, `setup`, `sin`)
- **Introduced:** MKT-4C
- **Why deferred:** Cluster names come from word-splitting differentiators without a stopword filter and without Unicode normalization. `Sin contratos largos` → `sin_informational`. `Diseñado específicamente` → `diseado_informational` (also has the accent strip bug).
- **Resolves at:** MKT-4D.
- **Sketch:** in `generate_keyword_plan`, drop stopwords from a small ES list (`sin`, `con`, `para`, `por`, `de`, `el`, `la`, `los`, `las`, `un`, `una`, `que`, `y`, `o`, `a`, `en`), normalize Unicode via `unicodedata.normalize("NFD", ...)` then strip combining marks. Refuse clusters of <4 chars or single-word generic terms.

### P-4C.5 — Hashtag generator strips accents incorrectly (`#Diseñado` → `#Diseado`)
- **Introduced:** MKT-4C
- **Why deferred:** Same root cause as P-4C.4 — naive ASCII strip instead of Unicode-aware normalization.
- **Resolves at:** MKT-4D (bundled with P-4C.4).
- **Sketch:** centralize the normalization in a `_slugify_for_hashtag(text)` helper; use NFD + strip Mn category + filter remaining non-alnum.

### P-4C.6 — `RefusingClaudeInvoker.complete()` message is stale
- **Introduced:** MKT-4C
- **Why deferred:** Cosmetic. Says "MKT-4A ships infrastructure only — wire one in MKT-4B" but MKT-4B already shipped. Should now read "no ANTHROPIC_API_KEY set or `anthropic` SDK not installed".
- **Resolves at:** any time; one-liner.

### P-4C.7 — Templates ignore `good_examples` / `bad_examples`
- **Introduced:** MKT-4C
- **Why deferred:** Out of scope here. The intake captures concrete patterns the client wants/hates ("post LinkedIn con command real + screenshot + frase técnica" / "hilos motivacionales") and the generator never reads them.
- **Resolves at:** MKT-4D.
- **Sketch:** at least one social post copy per channel should be seeded with a `good_examples` pattern when one exists. The Approval Pack should flag generated copy that matches a `bad_examples` pattern.

### P-4C.8 — Buyer persona quote and motivations are placeholders
- **Introduced:** MKT-4C
- **Why deferred:** Quote `"Necesito X sin tener que pensarlo demasiado."` and `Motivaciones: [único KPI repetido]` are template echos. Fixing this means actually thinking about pain → desire → quote chains per archetype.
- **Resolves at:** MKT-4D or later.

### P-4C.9 — Diagnostic section flags "Sin propuestas de valor declaradas" even when `additional_context` describes them
- **Introduced:** MKT-4C
- **Why deferred:** False positive caused by the diagnostic only checking `brief.product.value_props`. After MKT-4C, the normalizer DOES populate `value_props` for intakes with a clear em-dash separator, so this only triggers for prose-only intakes — but the diagnostic should also consider `additional_context`.
- **Resolves at:** MKT-4D.

### P-4C.10 — Channel rationale identical across all channels
- **Introduced:** MKT-4C
- **Why deferred:** `_rationale_for_channel(ch, audience)` returns the same template (`"Match con audiencia ({label}); rol esperado: {role}"`) for every channel. Channels have distinct dynamics (LinkedIn algorithm, X engagement, newsletter open rates) that the rationale should reflect.
- **Resolves at:** MKT-4D.

---

## MKT-4C items resolved in MKT-4D

- **P-4C.1** (brand_tone ignored) — **✅ resolved** via `tone_adjective` / `tone_connector` / `tone_opener` helpers used in social copies + email openers.
- **P-4C.2** (preferred_words not injected) — **✅ resolved** via `pick_preferred_word` woven into headline, hashtags, social copies (1 per channel), email openers.
- **P-4C.3** (placeholder phrase reused 6×) — **✅ resolved** by rewriting `generate_value_proposition` to compose headlines from real intake content. Pinned by `tests/strategy/test_content_quality.py` (5 tests assert the phrase never appears in headline, big_idea, email bodies, social copies, reels voiceovers).
- **P-4C.4** (keyword junk clusters) — **✅ resolved** via `first_meaningful_token` + Spanish stopword filter + `is_meaningful_keyword` rejection of stopwords / short / generic tokens.
- **P-4C.5** (hashtag accent strip) — **✅ resolved** via `make_hashtag` with Unicode NFD normalization. Pinned by `test_hashtag_for_accented_word_uses_nfd` + `test_hashtag_for_diseado_never_appears`.
- **P-4C.7** (good/bad examples ignored) — **✅ partially resolved** for bad_examples (matched as pattern → MEDIUM risk) and forbidden_words (matched against generated corpus → HIGH risk). Good_examples positive injection deferred to P-4D.3.

Still open from MKT-4C: P-4C.6 (stale RefusingClaudeInvoker message), P-4C.8 (buyer persona placeholders), P-4C.9 (partial; prose-only intakes still trigger false positive), P-4C.10 (channel rationale identical).

---

## From MKT-4D (template content quality pass)

### P-4D.1 — `tone_adjective` returns masculine form only
- **Introduced:** MKT-4D
- **Why deferred:** Produces grammar errors when applied to feminine nouns. Example: `"3 decisiones precisos"` (should be `precisas`). Needs gender-agreement infrastructure or per-call gender hint from the template.
- **Resolves at:** when an intake surfaces a feminine-noun-in-headline pattern that's worth fixing.
- **Sketch:** add a `tone_adjective(tone_words, *, gender="m"|"f")` parameter; templates pass the gender based on the noun being modified.

### P-4D.2 — Inconsistent capitalization after `:` in composed strings
- **Introduced:** MKT-4D
- **Why deferred:** Cosmetic. Some composed strings keep the second clause lowercase. Spanish style guides differ on this; not a hard bug.
- **Resolves at:** if a user complains.

### P-4D.3 — `good_examples` not used to seed content
- **Introduced:** MKT-4D
- **Why deferred:** `matches_bad_example_pattern` handles the negative case. The symmetric positive case (using `good_examples` to actually generate at least one copy in that style) needs a simple template selector. Out of scope for the cleanup pass.
- **Resolves at:** when a real intake shows good_examples concrete enough to template against.

### P-4D.4 — Email #3 still emits `[Insertar 2 casos cortos]` literal
- **Introduced:** MKT-4D (carries over from MKT-3A)
- **Why deferred:** Template explicitly defers customer cases to human review. Could be replaced with a `case_studies` field in the intake schema.
- **Resolves at:** when a case_studies intake field is designed.

### P-4D.5 — Single differentiator repeats across surfaces
- **Introduced:** MKT-4D
- **Why deferred:** With the placeholder gone, `differentiators[0]` (often `"Resuelve un dolor concreto: <pain>"`) appears in headline, big_idea, social bodies, reels voiceover. Less bad than the old placeholder, but still repetitive.
- **Resolves at:** next quality pass.
- **Sketch:** templates referencing `differentiators[0]` should rotate by surface kind so each emphasizes a different diff.

### P-4D.6 — Tone families catalog is small (10 families)
- **Introduced:** MKT-4D
- **Why deferred:** `_TONE_FAMILIES` covers patterns we have evidence for. Real intakes will surface new descriptors (`sarcástico`, `académico`) that fall back to neutral.
- **Resolves at:** when a real intake uses an unmapped tone word.

### P-4D.7 — Connector mid-sentence styling
- **Introduced:** MKT-4D
- **Why deferred:** `"concretamente,"` mid-sentence reads OK but starts lowercase when it's the second clause separator. Could be styled by context.
- **Resolves at:** with P-4D.2.
