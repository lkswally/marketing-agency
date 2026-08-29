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

---

## From MKT-4E (campaign execution task pack)

### P-4E.1 — Visual direction titles render empty in design tasks
- **Introduced:** MKT-4E
- **Why deferred:** `_design_tasks` reads `getattr(d, 'title', '')` from `VisualDirection`, but the upstream model uses a different field name in some shapes. Needs introspection of the actual field (probably `concept_name` or similar) and a one-line fix.
- **Resolves at:** when `core/visual/models.py` is touched again.

### P-4E.2 — Date-led view of the task pack
- **Introduced:** MKT-4E
- **Why deferred:** The Markdown renderer is category-led. Useful for "what's blocking us" reviews but not for weekly stand-ups where the operator wants "what's due this week" first. A date-led variant could live next to `render_markdown_pack`.
- **Resolves at:** when an operator requests it.

### P-4E.3 — Notion payload schema_version hardcoded
- **Introduced:** MKT-4E
- **Why deferred:** `"notion-export.v1"` is a literal string in `notion_payload.py`. Should live next to the pack contract pin (`CAMPAIGN_EXECUTION_TASK_PACK_VERSION`) so a future bump is a one-line change.
- **Resolves at:** at the first Notion schema revision.

### P-4E.4 — Per-task effort estimate / SLA
- **Introduced:** MKT-4E
- **Why deferred:** No `effort_minutes` or `sla_hours` field on `ExecutionTask`. Adding it later is additive but the factory needs heuristics per task kind. Useful for capacity planning.
- **Resolves at:** when an operator runs more than one campaign in parallel and asks for load balancing.

### P-4E.5 — Owner assignment helper
- **Introduced:** MKT-4E
- **Why deferred:** Today only `owner_hint` is populated (a role string). No mapping from role → actual person. Would need a per-tenant "team roster" intake field.
- **Resolves at:** when a multi-person team starts using the system in production.

### P-4E.6 — Sync the task pack to a real Notion database
- **Introduced:** MKT-4E
- **Why deferred:** MKT-4E ships the Notion-ready payload but does NOT call Notion. A separate block (MKT-5A or similar) can add the SDK call behind a `--push-to-notion` flag, with the same opt-in pattern as `--backend claude` (env var + extras).
- **Resolves at:** future block; explicitly out of scope here.

### P-4E.7 — Per-channel publishing tool selection
- **Introduced:** MKT-4E
- **Why deferred:** Social publishing task description says "Cargar la pieza en la herramienta de publicación del canal". The actual tool (Buffer, Hootsuite, Later, native) is undetermined. Could be a per-tenant config.
- **Resolves at:** when a tenant has a fixed tool stack.

---

## From MKT-5A (notion sync dry-run plan)

### P-5A.1 — Promote `depends_on` to a Notion relation property
- **Introduced:** MKT-5A
- **Why deferred:** The dry-run plan maps `depends_on` to a `rich_text` joined string. A real sync would prefer a `relation` property pointing at the same database. Needs a two-pass create (pages first, relations second) which the planner can model later.
- **Resolves at:** P-5A.2 (real sync block) or earlier if useful.

### P-5A.2 — Real Notion sync block (write path)
- **Introduced:** MKT-5A
- **Why deferred:** Out of scope here. The block ships infrastructure only — the real sync block would consume the plan + call Notion via the official SDK behind an opt-in `--push-to-notion` flag, using the same env-var + extras pattern as `--backend claude` (MKT-4B).
- **Resolves at:** future block; explicitly out of scope here.
- **Sketch:** new `core/notion_sync/sync.py` with `NotionSyncExecutor(client_factory=...)`. CLI flag `--push-to-notion`. Env vars `NOTION_TOKEN` + `NOTION_PARENT_PAGE_ID`. Tests with mocked SDK only; CI never hits Notion.

### P-5A.3 — Pin Channel select options from the strategy report
- **Introduced:** MKT-5A
- **Why deferred:** Channel options are open today; the sync would add options on first occurrence. Could be pinned by introspecting every channel in the report's `channel_recommendation` and the `suggested_pieces`.
- **Resolves at:** with P-5A.2 (worth doing before the first real sync).

### P-5A.4 — Split Notes into two rich_text blocks
- **Introduced:** MKT-5A
- **Why deferred:** `Notes` concatenates `description + notes` blindly. Notion caps rich_text at 2000 chars per BLOCK; we could legitimately use multiple blocks for description and notes separately.
- **Resolves at:** if real tasks exceed the cap in practice.

### P-5A.5 — Date-range view recommendation
- **Introduced:** MKT-5A
- **Why deferred:** The recommended database does not specify default views (board, table, timeline). A real sync could create them at database setup time.
- **Resolves at:** with P-5A.2.

### P-5A.6 — Per-tenant Notion workspace mapping
- **Introduced:** MKT-5A
- **Why deferred:** A multi-tenant setup needs per-client mapping: which Notion workspace, which parent page, which icon, which database_id when re-syncing. Could live in a `data/clients/<slug>/notion.json` config.
- **Resolves at:** when multi-tenant deployment is real.

### P-5A.7 — Real "task_blocked" handling on update path
- **Introduced:** MKT-5A
- **Why deferred:** The sync today is conceptually create-only. Re-syncing the same task (after a status change in MARKETING-AGENCY-OS) should UPDATE the Notion page, not create a duplicate. Needs a stable task_id ↔ page_id mapping.
- **Resolves at:** with P-5A.2.

---

## MKT-5A items resolved in MKT-5B

- **P-5A.2** (real Notion sync block, write path) — **✅ resolved**. `NotionSyncExecutor` + `NotionClientWriter` ship the write path behind `--write --confirm` + env vars + SDK availability. `RefusingNotionWriter` keeps the dry-run fallback uniform.
- **P-5A.7** (task_id ↔ page_id mapping for idempotency) — **✅ resolved** via `NotionSyncedPagesIndex` persisted at `<client>/notion_synced_pages/current.json`. Re-runs skip already-synced tasks; the writer is never called twice for the same task.

---

## From MKT-5B (notion sync writer)

### P-5B.1 — Retry policy for transient errors
- **Introduced:** MKT-5B
- **Why deferred:** ADR 0019 D-19.6 explicitly chose one attempt per task. Notion's `RateLimitError` is the most likely transient error; a backoff + 2-3 retries with jitter would recover most of them without burning quota.
- **Resolves at:** when production runs surface `RateLimitError` recurrently.
- **Sketch:** opt-in `retry: RetryPolicy | None = None` kwarg on `NotionClientWriter`. Each retry is a separate `NotionWriteAttempt` in the sink so the audit timeline stays granular.

### P-5B.2 — Batch / streaming endpoints
- **Introduced:** MKT-5B
- **Why deferred:** Notion API supports a `pages.create` per call; no batch endpoint exists. Bulk writes today are just N serial calls. Could be parallelised via `asyncio` with a small worker pool.
- **Resolves at:** if/when a campaign produces hundreds of tasks and sync latency matters.

### P-5B.3 — `update_page` for the subset of fields that change upstream
- **Introduced:** MKT-5B
- **Why deferred:** Today the writer is create-only and the executor refuses to touch already-synced pages. State changes inside MAOS (e.g. a task moving from `todo` to `done`) do NOT propagate to Notion. Adding `update_page` needs an explicit idempotency design (which fields are MAOS-owned vs operator-edited).
- **Resolves at:** when the operator declares a "MAOS-owned fields" contract.
- **Sketch:** add `update_page(page_id, properties)` to `NotionWriter`. Executor compares the task's current state against the last synced state; only sends a diff for MAOS-owned fields (Status, Due Date, Blocked Reason). Operator-edited fields (Description, Owner Hint) are never overwritten.

### P-5B.4 — Per-tenant `database_id` mapping
- **Introduced:** MKT-5B
- **Why deferred:** Today the env var `NOTION_TASKS_DATABASE_ID` is global. A multi-tenant deployment needs per-client database ids (different agencies → different workspaces).
- **Resolves at:** when multi-tenant deployment is real.
- **Sketch:** `data/clients/<slug>/notion.json` carries `database_id`, optional `parent_page_id`, optional `icon` override. The CLI reads it instead of the env var when present.

### P-5B.5 — Promote `Depends On` to a Notion relation property
- **Introduced:** MKT-5B
- **Why deferred:** Depends on `P-5A.1` (the planner change to emit relations). The writer would need a two-pass create: pages first, then patch each page with the relation. Today it's a rich_text string.
- **Resolves at:** after P-5A.1 lands.

### P-5B.6 — Cost / rate-limit dashboard
- **Introduced:** MKT-5B
- **Why deferred:** The audit trail already carries per-attempt records (mode, duration, ok, error_type, page_id). An aggregator could count attempts per run per client per day.
- **Resolves at:** when an operations review needs it.

### P-5B.7 — Real integration smoke test against a sandbox Notion workspace
- **Introduced:** MKT-5B
- **Why deferred:** All tests today are mocked. A `@pytest.mark.integration` job that runs against a real (sandbox) Notion workspace would catch SDK drift early.
- **Resolves at:** when a sandbox workspace + token are provisioned for CI.

### P-5B.8 — `mkt notion-sync --reset-index <task_id>` helper
- **Introduced:** MKT-5B
- **Why deferred:** To force a re-sync today the operator manually edits `notion_synced_pages/current.json`. A small CLI helper would be friendlier (clear by task_id, clear all, clear if Notion page does not exist).
- **Resolves at:** when an operator asks for it.

### P-5B.9 — Promote audit payload to `audit-trail.v2`
- **Introduced:** MKT-5B
- **Why deferred:** Events are wrapped in `note` with `payload.notion_sync.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

---

## From MKT-5C (n8n execution payload dry-run)

### P-5C.1 — Real n8n sync block (write path)
- **Introduced:** MKT-5C
- **Why deferred:** Out of scope here. MKT-5C ships data-only payloads. A future block would consume the persisted `N8nExecutionPayload` and POST each action to its webhook behind an opt-in `--push-to-n8n --confirm` flag, with the same gates as MKT-5B (`notion-sync --write --confirm`).
- **Resolves at:** future block; explicitly out of scope here.
- **Sketch:** new `core/n8n_sync/sender.py` with `N8nWebhookSender` ABC + `RefusingN8nSender` (default) + `HttpN8nSender` (lazy-imports `httpx`, behind `[notion-extras]` style optional dep `n8n`). CLI flag `--push-to-n8n --confirm`. Env vars `N8N_WEBHOOK_BASE_URL` + per-action overrides.

### P-5C.2 — Per-tenant webhook URL mapping
- **Introduced:** MKT-5C
- **Why deferred:** A multi-tenant deployment needs per-client webhook URLs (different agencies → different n8n workspaces or different routing).
- **Resolves at:** when multi-tenant deployment is real.
- **Sketch:** `data/clients/<slug>/n8n.json` carries per-action webhook URL overrides. The future sender resolves logical names → URLs through this config.

### P-5C.3 — Channel/tool selection hints in email + social payloads
- **Introduced:** MKT-5C
- **Why deferred:** Today the payload says "email_draft" without picking Mailchimp vs Resend; "social_post_draft" without picking Buffer vs Later. A future block can surface the operator's tool choice in the intake / brand config and propagate it.
- **Resolves at:** when a tenant has a fixed tool stack.

### P-5C.4 — Action subtypes for `telegram_notification`
- **Introduced:** MKT-5C
- **Why deferred:** Today there's one Telegram notification per campaign (a summary). Real ops needs more: alert when blocked, reminder when stalled, summary when completed. Could be modelled as `subtype` field on the action.
- **Resolves at:** when ops asks for it.

### P-5C.5 — Drive folder permissions hint
- **Introduced:** MKT-5C
- **Why deferred:** `drive_asset_folder` payload carries `share_with_role`. A real implementation needs concrete email/group ids, which live in tenant config.
- **Resolves at:** with P-5C.2.

### P-5C.6 — Action-level dispatch tracking
- **Introduced:** MKT-5C
- **Why deferred:** The model has `dispatched` + `failed` status values reserved but never emitted by the dry-run. They'll be set by the future real-sync block (P-5C.1) to record what n8n actually accepted vs rejected. Idempotency map will mirror MKT-5B's `synced_pages_index`.
- **Resolves at:** with P-5C.1.

### P-5C.7 — Promote audit payload to `audit-trail.v2`
- **Introduced:** MKT-5C
- **Why deferred:** Events are wrapped in `note` with `payload.n8n_execution_payload.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

---

## From MKT-6A (manual marketing analytics import)

### P-6A.1 — Real GA4 API import block
- **Introduced:** MKT-6A
- **Why deferred:** Out of scope here. Future block would consume Google's `google-analytics-data` SDK behind an opt-in `[ga4]` extra, with credential resolution from a service account JSON env var. Same pattern as MKT-4B (Anthropic) and MKT-5B (Notion).
- **Resolves at:** future block.
- **Sketch:** new `core/analytics/sources/ga4_real.py` with `GA4Importer(client_factory=...)`. Tests with mocked client; CI never hits GA4.

### P-6A.2 — Real Search Console API import block
- **Introduced:** MKT-6A
- **Why deferred:** Same pattern as P-6A.1. Different SDK (`google-api-python-client`).
- **Resolves at:** future block.

### P-6A.3 — Multiple snapshots per client (time-ranged)
- **Introduced:** MKT-6A
- **Why deferred:** Today the snapshot is one append-only blob. Comparing "last week" vs "week before" needs separate snapshots keyed by time range.
- **Resolves at:** when comparison analysis is needed.
- **Sketch:** snapshot id includes a date range tag; analyzer accepts `--since/--until` flags.

### P-6A.4 — Tunable thresholds via per-tenant config
- **Introduced:** MKT-6A
- **Why deferred:** `_SEO_LOW_CTR`, `_PAUSE_MIN_IMPRESSIONS`, etc. are module constants. A tenant with very different volumes (niche B2B vs viral consumer) may need different cutoffs.
- **Resolves at:** when a tenant complains about a recommendation.
- **Sketch:** `data/clients/<slug>/analytics.json` overrides; analyzer falls back to constants when absent.

### P-6A.5 — LLM-enriched rationale for recommendations
- **Introduced:** MKT-6A
- **Why deferred:** The analyzer's rationale text is templated. LLM enrichment could turn it into a richer human-readable explanation, behind an opt-in flag (`--rationale claude`).
- **Resolves at:** future block.
- **Sketch:** reuse MKT-4B's `ClaudeInvoker` ABC. Default RefusingInvoker; fallback to templated rationale.

### P-6A.6 — Snapshot delta analysis
- **Introduced:** MKT-6A
- **Why deferred:** Compare two snapshots / two time ranges and produce a delta recommendation pack (engagement up 30%, paid_search ROI down, etc.). Requires P-6A.3 first.
- **Resolves at:** with P-6A.3.

### P-6A.7 — Cross-link recommendations to strategy report
- **Introduced:** MKT-6A
- **Why deferred:** A recommendation like "pause paid_search" could link back to the specific channel rec in `CampaignStrategyReport`. The analyzer would need to load the report (optional) and produce structured "revise this section" hints.
- **Resolves at:** when an operator asks for closed-loop feedback into the strategy.

### P-6A.8 — Audit payload bump to `audit-trail.v2`
- **Introduced:** MKT-6A
- **Why deferred:** Events are wrapped in `note` with `payload.analytics_import.{action, ...}` and `payload.analytics_analysis.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-6A.9 — Deduplication on re-import
- **Introduced:** MKT-6A
- **Why deferred:** Re-importing the same file doubles the rows. A future revision could detect duplicate rows (same source + date + content_ref + metric_name) and skip them.
- **Resolves at:** when an operator reports inflated counts.

### P-6A.10 — Per-metric date range in the report
- **Introduced:** MKT-6A
- **Why deferred:** The recommendation pack doesn't surface the date range of the underlying data. A tenant reading the pack months later may not know which weeks the analysis covered.
- **Resolves at:** when the snapshot stops being append-only (P-6A.3).

---

## From MKT-6B (campaign feedback loop)

### P-6B.1 — Auto-promote suggested tasks into the next ExecutionTaskPack
- **Introduced:** MKT-6B
- **Why deferred:** The pack's `SuggestedTask` shape matches `ExecutionTask`. A future block can promote them on the next `mkt build-tasks` invocation behind an opt-in `--apply-feedback` flag.
- **Resolves at:** when the operator runs two campaigns in a row and asks for it.
- **Sketch:** new flag on `build-tasks`. Reads the latest `campaign_feedback_pack`, converts `SuggestedTask` instances to `ExecutionTask` (priority, category, channel, evidence_refs all transfer cleanly), prepends them to the next pack with `state=todo`.

### P-6B.2 — LLM-enriched executive summary
- **Introduced:** MKT-6B
- **Why deferred:** Today the summary is templated and short. LLM enrichment via the MKT-4B Claude invoker (`--summary claude` flag) could produce richer client-facing prose. Default stays templated.
- **Resolves at:** future block.

### P-6B.3 — Multi-period comparison
- **Introduced:** MKT-6B
- **Why deferred:** Compare this cycle's feedback pack with the previous one and surface deltas ("paid_search dropped 30% vs last cycle"). Requires P-6A.3 (time-ranged snapshots).
- **Resolves at:** with P-6A.3.

### P-6B.4 — Strategy report mutation hints
- **Introduced:** MKT-6B
- **Why deferred:** The planner observes "pause x" but does not propose an explicit diff to `CampaignStrategyReport.channel_recommendation`. A future block could emit a per-section diff that a copywriter applies to the next strategy run.
- **Resolves at:** when the operator wants to close the loop end-to-end.

### P-6B.5 — Per-tenant channel-priority thresholds
- **Introduced:** MKT-6B
- **Why deferred:** `_EMAIL_LOW_OPEN_RATE`, `_SOCIAL_MIN_IMPRESSIONS`, etc. are module constants. Mirrors P-6A.4; would land via the same per-tenant config file.
- **Resolves at:** with P-6A.4.

### P-6B.6 — Audit-trail bump to `audit-trail.v2`
- **Introduced:** MKT-6B
- **Why deferred:** Events are wrapped in `note` with `payload.campaign_feedback_pack.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

---

## From MKT-6C (feedback apply / next campaign iteration plan)

### P-6C.1 — Promote `SuggestedIterationTask` into the next `CampaignExecutionTaskPack`
- **Introduced:** MKT-6C
- **Why deferred:** Shape mirrors `ExecutionTask` deliberately so promotion is trivial — but invoking it must stay opt-in. The CLI today never mutates upstream packs.
- **Resolves at:** future block adding `mkt build-tasks --apply-iteration-plan` (or similar).
- **Sketch:** read the latest `next_campaign_iteration_plan`, map each `SuggestedIterationTask` to an `ExecutionTask` (priority/category/channel transfer cleanly), prepend to the next pack with `state=todo`, emit audit event.

### P-6C.2 — LLM-enriched executive summary
- **Introduced:** MKT-6C
- **Why deferred:** Default templated summary stays; an opt-in flag would route through the MKT-4B Claude invoker for richer prose.
- **Resolves at:** future block.

### P-6C.3 — Populate `create_new` iteration actions
- **Introduced:** MKT-6C
- **Why deferred:** `IterationActionKind.CREATE_NEW` is reserved but never emitted today; the structured `NewContentIdea` section covers the intent. A revision can emit `create_new` actions when a recommendation explicitly says "create".
- **Resolves at:** when a feedback pack surfaces explicit "create new" suggestions.

### P-6C.4 — Calendar diff vs previous cycle
- **Introduced:** MKT-6C
- **Why deferred:** Surface week-by-week shifts ("blog moved from week 1 to week 3") against the previous iteration plan. Requires historical iteration plans or P-6A.3's time-ranged snapshots.
- **Resolves at:** with P-6A.3.

### P-6C.5 — Strategy report mutation hints
- **Introduced:** MKT-6C
- **Why deferred:** Iteration plan says "channel promote x" but does not propose a structured diff against `CampaignStrategyReport.channel_recommendation`. Mirrors P-6B.4 from the iteration-plan side.
- **Resolves at:** with P-6B.4.

### P-6C.6 — Audit-trail bump to `audit-trail.v2`
- **Introduced:** MKT-6C
- **Why deferred:** Events are wrapped in `note` with `payload.next_campaign_iteration_plan.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-6C.7 — Funnel-stage hints in the calendar
- **Introduced:** MKT-6C
- **Why deferred:** Calendar entries do not differentiate "weeks 1-2 = awareness/launch" vs "weeks 3-4 = nurture/conversion". A revision can carry `funnel_stage` per entry to align with the strategy report's narrative arc.
- **Resolves at:** when an operator asks for explicit funnel sequencing.

---

## From MKT-6D (Google Analytics + Search Console read-only connectors)

### P-6D.1 — OAuth onboarding flow / credentials wizard
- **Introduced:** MKT-6D
- **Why deferred:** Today the operator must provision a service-account JSON manually and set `GOOGLE_APPLICATION_CREDENTIALS`. A future block can add a guided wizard (or a workspace OAuth flow) that produces the JSON without touching the GCP console.
- **Resolves at:** when several clients are onboarded and the manual flow becomes the bottleneck.

### P-6D.2 — Explicit `--from` / `--to` date range
- **Introduced:** MKT-6D
- **Why deferred:** Today the CLI uses a rolling 28-day lookback (override via `--lookback-days`). Multi-period comparisons (P-6B.3 / P-6C.4) will need explicit ranges; add `--from YYYY-MM-DD` / `--to YYYY-MM-DD` then.
- **Resolves at:** with P-6B.3.

### P-6D.3 — Multi-property / multi-site fan-out
- **Introduced:** MKT-6D
- **Why deferred:** One CLI invocation = one property / site. Agencies serving the same client across multiple GA4 properties or country-specific Search Console properties need fan-out.
- **Resolves at:** when an operator runs into the second-property case.
- **Sketch:** accept `--source ga4 --property-id X,Y,Z`, fan out internally, emit one report per identifier with the same `report_id` group key.

### P-6D.4 — Per-fetch cache
- **Introduced:** MKT-6D
- **Why deferred:** Repeated CLI calls within the same hour hit the upstream service. Cache by (source, identifier_fingerprint, window) with a short TTL (e.g. 1h).
- **Resolves at:** when the fetch volume becomes meaningful.

### P-6D.5 — Native `analytics-fetch.v1` audit envelope
- **Introduced:** MKT-6D
- **Why deferred:** Events are wrapped in `note` with `payload.analytics_fetch.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-6D.6 — Additional read-only connectors
- **Introduced:** MKT-6D
- **Why deferred:** The ABC is generic; same shape can host Bing Webmaster Tools, Meta Insights, TikTok Insights, LinkedIn Page Analytics — each as a new subclass + `SUPPORTED_SOURCES` entry + normaliser.
- **Resolves at:** when the operator needs metrics from a non-Google source the manual importer doesn't cover.

### P-6D.7 — Google Ads connector  ✅ RESOLVED in MKT-6E
- **Introduced:** MKT-6D
- **Resolved at:** MKT-6E — `core/analytics/connectors/google_ads.py` with `GoogleAdsReadOnlyConnector` using `GoogleAdsService.search_stream` only.
- **Notes:** Read-only strict. Cardinal pins grep-asserted.

---

## From MKT-6E (Google Ads read-only connector)

### P-6E.1 — `search_term_view` query for negative-keyword candidates
- **Introduced:** MKT-6E
- **Why deferred:** The connector currently queries the `ad_group` view only. Negative-keyword detection requires `FROM search_term_view` with `segments.search_term_match_type` and per-term metrics. Drops nicely into the existing connector — additional GAQL query + normaliser branch + analyzer rule.
- **Resolves at:** when an operator hits a campaign with budget bleed on irrelevant queries.

### P-6E.2 — `keyword_view` query for keyword-level performance
- **Introduced:** MKT-6E
- **Why deferred:** Same shape as P-6E.1 — a second GAQL query at the keyword level (`ad_group_criterion.keyword.text`, `ad_group_criterion.keyword.match_type`).
- **Resolves at:** with P-6E.1.

### P-6E.3 — `ad_group_ad` query for creative-level CTR detection
- **Introduced:** MKT-6E
- **Why deferred:** Low-CTR ad detection at the creative level (responsive search ads, individual ad variants) requires `FROM ad_group_ad` with headline / description segments.
- **Resolves at:** when copy iteration becomes a recurring ask.

### P-6E.4 — `landing_page_view` query for landing-page opportunities
- **Introduced:** MKT-6E
- **Why deferred:** Landing-page optimisation suggestions need `FROM landing_page_view` (expanded URL + per-URL metrics) plus a join against the GA4 landing-page metrics for cross-source validation.
- **Resolves at:** when an operator wants funnel-stage analysis.

### P-6E.5 — Audience / demographic segmentation
- **Introduced:** MKT-6E
- **Why deferred:** `segments.audience`, `segments.age_range`, `segments.gender` add a dimensional layer the current normaliser does not encode. Requires extending `MetricRow.dimension` semantics or a richer secondary-dimension shape.
- **Resolves at:** future block.

### P-6E.6 — Multi-customer MCC fan-out
- **Introduced:** MKT-6E
- **Why deferred:** One CLI invocation = one `GOOGLE_ADS_CUSTOMER_ID`. Agencies on an MCC reading 10+ accounts in one pass need fan-out.
- **Resolves at:** when the operator runs into the second-account case.
- **Sketch:** accept `--customer-id A,B,C`, fan out internally, emit one report per customer with a shared `group_id`.

### P-6E.7 — Native analyzer rules for Google Ads detections
- **Introduced:** MKT-6E
- **Why deferred:** The connector lands rows; the analyzer currently rolls them up at the channel level. Explicit "pause campaign X — high spend / 0 conversions in 28 days" or "negative-keyword candidate: <term>" recommendations require new rules in `core/analytics/analyzer.py` and `core/feedback/planner.py`.
- **Resolves at:** when MKT-6E rows are flowing through the snapshot regularly.

### P-6E.8 — Native `analytics-fetch.v1` audit envelope for Google Ads
- **Introduced:** MKT-6E
- **Why deferred:** Same trade-off as P-6D.5 — events wrapped in `note` with `payload.analytics_fetch.{action, source, ...}`.
- **Resolves at:** bundled with the next audit-trail bump.

---

## From MKT-6F (Google Ads analyzer rules)

### P-6F.1 — Per-tenant threshold overrides
- **Introduced:** MKT-6F
- **Why deferred:** Today `_HIGH_SPEND_ZERO_CONV_COST`, `_LOW_CTR_THRESHOLD`, etc. are module constants tuned for a generic "small B2B" baseline. Different tenants need different thresholds (e-commerce vs lead gen vs SaaS).
- **Resolves at:** when an operator hits a baseline mismatch on a second tenant.
- **Sketch:** load `<root>/<client>/ads-analyzer-config.json` (optional) with float overrides per threshold; fall back to module constants.

### P-6F.2 — Search-term-level insights
- **Introduced:** MKT-6F
- **Why deferred:** Negative-keyword candidate detection requires search-term rows in the snapshot. Depends on P-6E.1 (search-term query at the connector).
- **Resolves at:** with P-6E.1.

### P-6F.3 — Ad-creative-level insights
- **Introduced:** MKT-6F
- **Why deferred:** Low-CTR detection at the creative level (per ad variant) requires creative-level rows. Depends on P-6E.3 (`ad_group_ad` query at the connector).
- **Resolves at:** with P-6E.3.

### P-6F.4 — Landing-page cross-validation against GA4
- **Introduced:** MKT-6F
- **Why deferred:** `review_landing` today fires from CTR/conversion-rate mismatch. A future rule can cross-validate against GA4 landing-page rows (bounce rate, sessions) to lift signal quality.
- **Resolves at:** when both Ads and GA4 rows are reliably in the snapshot.

### P-6F.5 — Auto-promotion of insights into the feedback / iteration pack
- **Introduced:** MKT-6F
- **Why deferred:** `AdsInsightAction.PAUSE_CANDIDATE` / `SCALE_CANDIDATE` / `IMPROVE_AD_COPY` map cleanly to MKT-6B `ContentSuggestion` / MKT-6C `IterationAction`. A future block can opt-in promote them on `mkt feedback-plan --include-ads-insights` and `mkt apply-feedback --include-ads-insights`.
- **Resolves at:** future block.

### P-6F.6 — LLM-enriched rationale
- **Introduced:** MKT-6F
- **Why deferred:** Today rationales are templated. An opt-in flag could route through the MKT-4B Claude invoker for richer prose (especially around `review_campaign` / `review_landing`).
- **Resolves at:** future block.

### P-6F.7 — Native `google_ads_insight_pack.v1` audit envelope
- **Introduced:** MKT-6F
- **Why deferred:** Events are wrapped in `note` with `payload.google_ads_insight_pack.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-6F.8 — Multi-period comparison (this cycle vs last cycle)
- **Introduced:** MKT-6F
- **Why deferred:** The analyzer sees one snapshot. Comparing this cycle's insights against the previous cycle's pack would surface deltas ("CPA on Brand campaign was median × 1.2, now median × 2.5"). Requires P-6A.3 time-ranged snapshots.
- **Resolves at:** with P-6A.3.

---

## From MKT-6G (Ads insights to feedback loop integration)

### P-6G.1 — Opt-in promotion of `AdsSuggestedTask` into `CampaignFeedbackPack`  ✅ RESOLVED in MKT-6H
- **Introduced:** MKT-6G
- **Resolved at:** MKT-6H — `mkt feedback-plan --include-ads-bridge` via `core/ads_promoter/`.

### P-6G.2 — Opt-in promotion into `CampaignExecutionTaskPack`  ✅ RESOLVED in MKT-6H
- **Introduced:** MKT-6G
- **Resolved at:** MKT-6H — `mkt build-tasks --include-ads-bridge`.

### P-6G.3 — Opt-in promotion into `NextCampaignIterationPlan`  ✅ RESOLVED in MKT-6H
- **Introduced:** MKT-6G
- **Resolved at:** MKT-6H — `mkt apply-feedback --include-ads-bridge`.

### P-6G.4 — Real negative-keyword candidate extraction
- **Introduced:** MKT-6G
- **Why deferred:** The bridge has the wiring for `AdsKeywordProposal` but the source data (search-term-level rows) needs P-6E.1 (connector query) and P-6F.2 (analyzer rule). Once both land, the bridge will emit real candidates with zero code change here.
- **Resolves at:** with P-6E.1 + P-6F.2.

### P-6G.5 — Cross-channel comparison (Ads vs GA4 / Search Console)
- **Introduced:** MKT-6G
- **Why deferred:** A high-priority bridge pack could include "Brand keyword: paid CPA $25, organic CTR 8% on same query" comparisons. Requires search-term-level data in both connectors.
- **Resolves at:** future block once search-term data is reliable.

### P-6G.6 — LLM-enriched rationale
- **Introduced:** MKT-6G
- **Why deferred:** Today rationales are templated. Opt-in flag could route through MKT-4B Claude invoker for richer client-facing prose.
- **Resolves at:** future block.

### P-6G.7 — Native `ads_feedback_bridge_pack.v1` audit envelope
- **Introduced:** MKT-6G
- **Why deferred:** Events wrapped in `note` with `payload.ads_feedback_bridge_pack.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-6G.8 — Multi-period delta vs previous bridge pack
- **Introduced:** MKT-6G
- **Why deferred:** Compare this cycle's bridge pack against the previous one ("3 new pause candidates this cycle, 2 carried over"). Requires historical bridge packs or P-6A.3 time-ranged snapshots.
- **Resolves at:** with P-6A.3.

---

## From MKT-6H (ads bridge promoter opt-in)

### P-6H.1 — Promote `AdsKeywordProposal` entries into the feedback pack
- **Introduced:** MKT-6H
- **Why deferred:** Today the bridge emits zero proposals (no search-term data). Once P-6E.1 lands, proposals will be real and worth promoting — likely as `SuggestedTask` entries with category `operational` plus a sentinel marker.
- **Resolves at:** with P-6E.1.

### P-6H.2 — Filter / select subset of recommendations to promote
- **Introduced:** MKT-6H
- **Why deferred:** Today `--include-ads-bridge` is all-or-nothing. A future flag could narrow to high-priority only (`--include-ads-bridge=high`) or to specific kinds (`--include-ads-bridge=pause_review,scale_opportunity`).
- **Resolves at:** when operators hit promotion volume that needs trimming.

### P-6H.3 — Dry-run preview of what would be promoted
- **Introduced:** MKT-6H
- **Why deferred:** `--include-ads-bridge --dry-run` could print the proposed promotions + counts without persisting. Useful when the bridge pack has many high-priority items.
- **Resolves at:** future block.

### P-6H.4 — Promote into `ExecutionTask.depends_on` graph
- **Introduced:** MKT-6H
- **Why deferred:** Today promoted execution tasks are standalone. A future version could link them to the underlying campaign tasks via `depends_on` so the kanban respects dependencies.
- **Resolves at:** when operators ask for graph-aware promotion.

### P-6H.5 — Native `ads_bridge_promotion.v1` audit envelope
- **Introduced:** MKT-6H
- **Why deferred:** Events wrapped in `note` with `payload.ads_bridge_promotion.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-6H.6 — Multi-source promotion
- **Introduced:** MKT-6H
- **Why deferred:** Today the promoter handles only `AdsFeedbackBridgePack`. If additional source bridges land (e.g. an organic-search bridge), the flag could become a multi-value list or split into one flag per source.
- **Resolves at:** when a second bridge source is introduced.

---

## From MKT-7A (image generation job pack)

### P-7A.1 — Per-tenant provider heuristic override
- **Introduced:** MKT-7A
- **Why deferred:** Today `_PIECE_TYPE_TO_PROVIDER` is a module constant. Different tenants prefer different providers (cost / brand / agency template). A tenant-specific config file could override per-piece-type.
- **Resolves at:** when an operator hits a tenant-baseline mismatch.

### P-7A.2 — Per-job cost estimate
- **Introduced:** MKT-7A
- **Why deferred:** Cost is provider × dimensions × variants. Requires a static price table per provider and currency normalisation. Operator-facing surface needs design.
- **Resolves at:** when integrated providers ship (with P-7A.6).

### P-7A.3 — Reference image attachment (style transfer inputs)
- **Introduced:** MKT-7A
- **Why deferred:** Some providers accept a reference image (style transfer / IP-Adapter). Requires a model field for the source asset id + safety pin that the bridge does not embed binary data.
- **Resolves at:** with the first integration block that supports reference inputs.

### P-7A.4 — Multi-output jobs (one prompt → N renders)
- **Introduced:** MKT-7A
- **Why deferred:** Today one variant = one job. A future job could declare `n_outputs: int` with per-output review gates.
- **Resolves at:** when operators ask for batched generation.

### P-7A.5 — Job grouping by campaign / launch wave
- **Introduced:** MKT-7A
- **Why deferred:** Jobs are flat per pack today. Grouping (e.g. "Launch wave 1" / "Always-on") would help operators tackle them in batches in the Ads/CMS UI.
- **Resolves at:** when a multi-wave campaign hits the agency.

### P-7A.6 — Real provider integration with `generated` state + asset URI
- **Introduced:** MKT-7A
- **Why deferred:** The entire point of MKT-7A is to ship the job-pack contract WITHOUT touching any provider. A separate block (likely MKT-7B) will implement one or more provider adapters (read-write) with explicit opt-in flags, idempotence, audit envelopes and the `generated` state.
- **Resolves at:** with MKT-7B.

### P-7A.7 — Native `image_generation_job_pack.v1` audit envelope
- **Introduced:** MKT-7A
- **Why deferred:** Events wrapped in `note` with `payload.image_generation_job_pack.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-7A.8 — Promote `ready_for_generation` jobs into `CampaignExecutionTaskPack`
- **Introduced:** MKT-7A
- **Why deferred:** Mirrors the MKT-6H pattern. Opt-in flag on `mkt build-tasks --include-image-jobs` could fold each ready job into the operational task pack as a "generate image" task assigned to a designer / provider operator.
- **Resolves at:** future block.

---

## From MKT-7B (image provider selection & dry run)

### P-7B.1 — Per-tenant override of provider profiles
- **Introduced:** MKT-7B
- **Why deferred:** Today `DEFAULT_PROVIDER_PROFILES` is a module constant. Different tenants prefer different providers (cost / brand / agency template). A `<root>/<client>/image-providers-config.json` could override per-provider scores and cost estimates.
- **Resolves at:** when an operator hits a tenant-baseline mismatch.

### P-7B.2 — Per-job cost adjusted for dimensions + variants count
- **Introduced:** MKT-7B
- **Why deferred:** Today the cost estimate is the provider's flat per-image price. Real cost depends on dimensions × variants count × pricing tier. Requires per-provider price tables.
- **Resolves at:** when integrated providers ship (with MKT-7C).

### P-7B.3 — Live provider availability check
- **Introduced:** MKT-7B
- **Why deferred:** Would require HTTP — explicitly forbidden in MKT-7B. A future block can probe each provider's health endpoint and downgrade the score if degraded.
- **Resolves at:** with MKT-7C.

### P-7B.4 — Per-tenant override of weight overlays
- **Introduced:** MKT-7B
- **Why deferred:** Today `_PIECE_TYPE_WEIGHT_OVERLAYS` is a module constant. Per-tenant overrides could be loaded alongside provider profiles (P-7B.1).
- **Resolves at:** with P-7B.1.

### P-7B.5 — Real provider integration with `generated` status
- **Introduced:** MKT-7B
- **Why deferred:** The entire point of MKT-7B is to ship the analysis + dry-run WITHOUT touching any provider. A separate block (MKT-7C) will implement one or more adapters (opt-in, idempotent, feature-flagged) and emit a real "generated" status with the asset URI.
- **Resolves at:** with MKT-7C.

### P-7B.6 — Native `image_provider_recommendation_pack.v1` audit envelope
- **Introduced:** MKT-7B
- **Why deferred:** Events wrapped in `note` with `payload.image_provider_recommendation_pack.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-7B.7 — Cross-pack diff vs previous plan
- **Introduced:** MKT-7B
- **Why deferred:** Compare this plan against the previous one ("OpenAI dropped after a pricing update — re-score"). Requires historical recommendation packs.
- **Resolves at:** when operators ask for provider-stability tracking.

---

## From MKT-8A (alpha pilot readiness + ATLAS bridge contract)

### P-8A.1 — Real ATLAS execution
- **Introduced:** MKT-8A
- **Why deferred:** MKT-8A is intentionally read-only over ATLAS. The operator copies briefs manually. A future block (likely MKT-8B) can add an opt-in `mkt atlas-execute` that POSTs the brief to a real ATLAS endpoint with idempotence + audit.
- **Resolves at:** when ATLAS exposes a stable ingestion API.

### P-8A.2 — Per-tenant overrides for bridge defaults
- **Introduced:** MKT-8A
- **Why deferred:** The factory currently builds one auto-generated section list per landing (hero → value_prop → proof → cta) and one default block list per page design. A future block can load `<root>/<client>/atlas-bridge-config.json` with per-tenant overrides.
- **Resolves at:** when a tenant hits the default-template ceiling.

### P-8A.3 — Handoff validation pass
- **Introduced:** MKT-8A
- **Why deferred:** Today validation = Pydantic. A future linter could enforce richer rules ("acceptance criteria must mention measurable outcomes", "every section must reference at least one asset"). Useful when ATLAS returns false positives in QA.
- **Resolves at:** when operators ask for richer checks at handoff time.

### P-8A.4 — Real landing MVP / portal MVP
- **Introduced:** MKT-8A
- **Why deferred:** No landing is generated in this block. A future MKT-9A could ship a minimal portal that hosts the handoff briefs as a read-only operator dashboard — still not generating the landing itself.
- **Resolves at:** with the post-pilot retrospective.

### P-8A.5 — `_alpha_pilot_notes` strict-mode validator
- **Introduced:** MKT-8A
- **Why deferred:** The intake template's safety flags are advisory. A future `mkt intake --strict-alpha-pilot` could refuse to proceed when any flag is `true`.
- **Resolves at:** before the second real pilot.

### P-8A.6 — ATLAS round-trip capture
- **Introduced:** MKT-8A
- **Why deferred:** Today the operator captures ATLAS's response in their own log. A future block can persist `atlas_handoff_response/current.json` so the audit trail closes the loop.
- **Resolves at:** with P-8A.1.

### P-8A.7 — Native `atlas_handoff_brief.v1` audit envelope
- **Introduced:** MKT-8A
- **Why deferred:** Events wrapped in `note` with `payload.atlas_handoff_brief.{action, ...}`. Same trade-off as every previous block.
- **Resolves at:** bundled with the next audit-trail bump.

### P-8A.8 — Localised brief output
- **Introduced:** MKT-8A
- **Why deferred:** Markdown labels are in English; the body copy honours the client locale because it comes verbatim from the strategy report. A future block can localise the section headers / banner text per `intake.locale`.
- **Resolves at:** when a non-English-speaking ATLAS team needs the brief in their language.

---

## From MKT-9A (read-only portal MVP)

### P-9A.1 — Auth + multi-user
- **Introduced:** MKT-9A
- **Why deferred:** The portal is single-user, single-machine. Multi-user requires auth (Streamlit-Authenticator or external SSO) and a session story.
- **Resolves at:** when the agency wants to share the portal across operators.

### P-9A.2 — Auto-refresh on disk changes
- **Introduced:** MKT-9A
- **Why deferred:** Today the operator refreshes the browser to pick up new packs. A `watchdog`-backed file-mtime poll + `st.rerun()` could auto-refresh.
- **Resolves at:** when operators run the portal alongside long pipelines.

### P-9A.3 — Export checklist + summary to PDF
- **Introduced:** MKT-9A
- **Why deferred:** Useful for client review meetings. Streamlit has no native PDF export — would require WeasyPrint or a server-side render. Keeps the portal lean for now.
- **Resolves at:** when an operator needs a take-home checklist.

### P-9A.4 — Cycle-vs-cycle comparison view
- **Introduced:** MKT-9A
- **Why deferred:** Once a client has multiple cycles, comparing this cycle's packs against the previous one would help spot drift. Requires P-6A.3 (time-ranged snapshots) first.
- **Resolves at:** with P-6A.3.

### P-9A.5 — Full-text search across rendered Markdown
- **Introduced:** MKT-9A
- **Why deferred:** Streamlit has a built-in input but no native indexed search. A simple substring scan over each pack's MD would work; per-client whoosh / sqlite-fts is overkill for now.
- **Resolves at:** when packs grow large enough that grepping the outputs dir becomes annoying.

### P-9A.6 — Editing opt-in (explicitly out of scope today)
- **Introduced:** MKT-9A
- **Why deferred:** The user spec for MKT-9A explicitly forbade editing. A future block can add a feature-flagged edit mode that produces a diff + audit event without touching disk silently.
- **Resolves at:** only when operators explicitly ask for it.

---

## From MKT-9B (Alpha Pilot 1 findings — LEXIA)  ✅ RESOLVED

- **Introduced:** MKT-9B
- **Resolved at:** MKT-9B (same block) — fixed `portal/pack_registry.py` kind
  mismatches (`"strategy"` → `campaign_strategy_report`, `n8n_execution_plan`
  → `n8n_execution_payload`) that made the portal report existing packs as
  MISSING; `core/atlas_bridge/factory.py` now persists one JSON per handoff
  kind (landing/branding/page_design) instead of all three overwriting a
  shared `current.json`; templated-backend quality lift in
  `core/strategy/templates.py` (executive summary weaves a preferred word,
  channel rationales are no longer identical boilerplate, diagnosis surfaces
  competitor names + forbidden words).
- **Notes:** 14 net-new tests across 4 files. No new features, no new
  external integrations — pure correctness + templated-quality fix triggered
  by running the pipeline against the real `examples/intake/lexia.json`.
  `data/lexia/` added to gitignore as the per-pilot working directory
  (superseded by the broader `data/*` pattern from MKT-10A).

## From MKT-9C (legal domain templated outputs)  ✅ RESOLVED

- **Introduced:** MKT-9C
- **Resolved at:** MKT-9C (same block) — added domain-aware extraction
  helpers to `core/strategy/templates.py` (`_extract_product_features`,
  `_detect_anti_pattern_tools`, `_extract_pains_from_intake`,
  `_sanitize_forbidden`) so a real-business intake (LEXIA) produces
  domain-specific pain points, headlines, keyword clusters, social copy and
  reels voiceover instead of generic SaaS boilerplate.
- **Notes:** 16 new tests in `tests/strategy/test_mkt9c_legal_domain_outputs.py`.
  No new module, no new dependency, no API call, no Claude — pure templated
  improvements over the existing deterministic backend.

## From MKT-9D (industry-aware tone templates)  ✅ RESOLVED

- **Introduced:** MKT-9D
- **Resolved at:** MKT-9D (same block) — added a `"legal-pro"` tone family
  and `tone_family_for_brief(brief)` three-tier detector (industry signal →
  audience-description signal → brand-tone fallback) to
  `core/strategy/style.py`; wired `generate_social_post_drafts`,
  `generate_email_sequence` and `generate_reels_script_pack` in
  `core/strategy/templates.py` to select copy per detected tone family so
  legal/legaltech intakes stop reading like generic SaaS marketing.
- **Notes:** 12 new tests in `tests/strategy/test_mkt9d_industry_tone.py`.
  Existing `tone_adjective` / `tone_connector` / `tone_opener` helpers kept
  unchanged for backward compat with non-strategy callers. No new modules,
  no new dependencies, no Claude.

---

## From MKT-10X (market intelligence + UTM foundation)

### P-10X.1 — Real intelligence adapters (no dry-run)
- **Introduced:** MKT-10X
- **Why deferred:** All 5 adapters (Google Trends, Reddit, YouTube, Meta Ads, competitor monitor) are dry-run only. No SDK imports, no HTTP, no credentials.
- **Resolves at:** when the operator enables a specific integration.

### P-10X.2 — UTM link validator
- **Introduced:** MKT-10X
- **Why deferred:** Generated UTM URLs are structurally valid but not tested against live pages. A future block could run a dry-run `HEAD` check on `final_url`.
- **Resolves at:** when URL validation becomes operationally useful.

---

## From MKT-10Y (Windows pytest baseline stabilization)

### P-10Y.1 — Linux / macOS baseline doc
- **Introduced:** MKT-10Y
- **Why deferred:** `docs/runtime/windows-test-baseline.md` covers Windows only. A parallel doc for POSIX does not exist because no POSIX-specific failures have been observed.
- **Resolves at:** if a non-Windows contributor encounters a CI anomaly.

---

## From MKT-10B (time-ranged metrics snapshots)  ✅ RESOLVED

- **Introduced:** MKT-10B
- **Resolved at:** MKT-10B (same block) — `MetricsSnapshot` gained
  `period_start` / `period_end` / `period_label` / `source` fields;
  deterministic `snapshot_entity_id(source, period_start, period_end)` and
  `snapshot_id_from_period(...)` (SHA-256) make re-imports of the same
  period idempotent instead of duplicating; `core/analytics/snapshot_repo.py`
  ships `list_metric_snapshots` / `load_metric_snapshot` /
  `latest_metric_snapshot`; `AnalyticsImporter` and `AnalyticsFetchService`
  dual-write — every import/fetch still updates the `"current"` singleton
  (backward compat for the analyzer / feedback / iteration planners) AND, when
  a period is known, the period-keyed snapshot. CLI: `--period-start` /
  `--period-end` / `--period-label` on `import-metrics`; `--period-label` on
  `analytics-fetch`.
- **Notes:** 22 new tests in `tests/analytics/test_snapshot_repo.py`. Full
  suite green (1792 passed), ruff clean, ATLAS untouched. This item directly
  unblocks **P-6A.3** (multiple snapshots per client) — every deferred item
  cross-referencing P-6A.3 (P-6B.3, P-6C.4, P-6F.8, P-6G.8, P-9A.4) can now
  build on the period-snapshot primitive shipped here, though the comparison
  logic itself (deltas, cycle-vs-cycle views) is still NOT implemented and
  remains open at those items.

---

## From MKT-11A (application services foundation)  ✅ RESOLVED (scoped)

- **Introduced:** MKT-11A
- **Resolved at:** MKT-11A (same block) — new `core/application/` package
  (`context.py` → `OperationContext`, `result.py` → `OperationResult` /
  `OperationError` / `Artifact` / `OperationWarning`, `artifacts.py` →
  centralized, path-traversal-guarded `write_artifacts`,
  `services/{seo,analytics,approvals}.py`). `mkt seo-report` migrated
  behaviour-identically (its 25 pre-existing tests pass unmodified). New
  commands `mkt approvals list` / `mkt approvals show` / `mkt approve` /
  `mkt reject` wrap the existing `ApprovalPackBuilder.approve()/reject()`
  domain methods — no duplication — with two policy decisions enforced at
  the application layer per D-11.5: idempotent success (with warning, no
  new audit event) when a pack is already in the requested terminal
  state, and a mandatory non-empty `--reason` to reject. Read-only
  Analytics snapshot services (`list_snapshots` / `get_snapshot` /
  `get_latest_snapshot`) expose the MKT-10B `snapshot_repo` helpers
  through the application layer for the first time — no CLI command
  added (none existed to preserve).
- **Notes:** 75 new tests (`tests/application/`, `tests/cli/test_cli_approvals.py`).
  Full suite green (1893 passed), ruff clean, `portal/` untouched (its 52
  read-only tests re-verified unmodified), ATLAS untouched. Full
  inventory + migration rationale in
  `docs/MKT-11A-Application-Services-Inventory.md`; target architecture
  in `docs/MKT-11-Control-Center-Architecture.md`.
- **Deliberately NOT done in this block** (see inventory §6 for the
  complete list): the other ~26 CLI commands remain unmigrated
  (`run-campaign` explicitly excluded — needs the job contract from
  D-11.7 first); the flat-vs-per-client output layout inconsistency
  found in the inventory (F-1) was preserved, not unified — unifying it
  is a behaviour change and belongs in its own block; the 3 CLI-side
  hand-rolled audit builders (`build-tasks`, `analyze-metrics`, `intake`)
  were not migrated into their domain services; the audit reader
  (`read_audit_events`) was not hardened (D-11.8 — still loads every
  JSONL file into memory, still raises on the first corrupt line); no
  job contract for long-running operations (D-11.7); no FastAPI, no
  Next.js, no Control Center UI (`control_center/` does not exist yet —
  that is MKT-11B+).

---

## From MKT-11B (approval operations)  ✅ RESOLVED (scoped)

- **Introduced:** MKT-11B
- **Resolved at:** MKT-11B (same block) — extended the MKT-11A
  `core/application/services/approvals.py` (not rebuilt; the inventory in
  `docs/MKT-11B-Approval-Operations-Inventory.md` found `list_pending` /
  `show` / `approve` / `reject` already shipped) with: **filters** on
  `list_pending` — `client_slug`, `status` (bypasses the default
  pending/blocked filter when given), `limit` — all backed by real
  persistence fields; **`campaign_id` and date-range filters were
  explicitly NOT implemented** — `ApprovalPack` has no `campaign_id`
  field and only a single `"current"` pack per client exists (no
  history), so those filters would have no honest semantics (documented
  in the inventory, not silently skipped). **`--approval-id`** is
  verification-only (D-11B.2) — compared against the loaded pack's
  `pack_id`, mismatch → `NOT_FOUND`; no new index, no history, no new
  persistence. **Role authorization** (D-11.6) via new
  `core/application/policies.py::check_can_decide_approval` — `VIEWER`
  and `ANALYST` are really blocked (`ErrorCode.PERMISSION_DENIED`);
  `OPERATOR`/`APPROVER`/`ADMIN` are allowed. `OPERATOR` staying allowed
  is a deliberate compatibility resolution, not an oversight: the
  pre-11B contract already permitted any actor (nothing gated approval
  before), and the MKT-11B role matrix's own carve-out — *"operator: no
  puede aprobar salvo que el contrato actual lo permita"* — is satisfied
  by that pre-existing reality. This keeps all 32 MKT-11A regression
  tests green with zero modification. **`audit_event_id` bug fix**: MKT-11A
  populated this field from `memory.last_audit_hash(...)` (the hash-chain
  tail); it now holds the real `AuditTrailEvent.event_id`, read back via
  `read_audit_events(...)` since `ApprovalPackBuilder._transition()`
  doesn't return the event object it builds. New
  `core/application/exit_codes.py` — first centralized, differentiated
  exit-code table for the CLI (`0/2/3/4/5/6/70`); every other pre-11B
  command keeps its own `0/2` mapping unchanged (additive, not
  retroactive). CLI: `mkt approvals list --client/--status/--limit`,
  `mkt approvals show --approval-id`, `mkt approve`/`mkt reject
  --approval-id --correlation-id`.
- **Notes:** 43 new tests (`tests/application/test_approvals_service_mkt11b.py`,
  `tests/cli/test_cli_approvals_mkt11b.py`), kept in separate files from
  the MKT-11A regression pins so the diff stays legible. Exactly 4
  existing CLI assertions (in `tests/cli/test_cli_approvals.py`) were
  updated — not their function names, not their setup, only the exit-code
  literal (`2` → `3` or `4`) — because differentiating those codes was
  this block's own explicit, approved requirement; every other assertion
  in that file, and all 18 tests in `tests/application/test_approvals_service.py`,
  are untouched. Full suite green, ruff clean, `portal/` untouched (its
  read-only pins re-verified), `run-campaign` untouched, ATLAS untouched.
- **Deliberately NOT done in this block:** `campaign_id` / date-range
  filters (no domain field / no history — see above); a global `--role`
  CLI flag (not in the confirmed CLI flag list; role is only exercised
  directly at the service layer in this block's tests); `run-campaign`
  as a service (still waiting on the job contract, D-11.7); jobs/queue/
  worker; FastAPI; Next.js/React; full authentication/sessions; the
  visual Approval Queue; automatic publishing; Market Intelligence;
  Learning Engine; Decision Engine.

---

## From MKT-11C (job execution foundation)  ✅ RESOLVED (scoped)

- **Introduced:** MKT-11C
- **Resolved at:** MKT-11C (same block) — new `core/jobs/` package:
  `models.py` (`JobRecord`, `JobState` 6-state machine incl.
  `WAITING_APPROVAL`, `JobOutcome`/`JobOutcomeStatus` as the explicit
  handler→runner contract — never inferred from strings), `registry.py`
  (`JobRegistry`, `OperationSpec` — no dynamic import, no `eval`, no
  resolution by function name; unregistered operation is
  `ErrorCode.UNKNOWN_OPERATION`, distinct from `INVALID_INPUT`),
  `repository.py` (one file per job, no singleton, full history,
  `sanitize_params()` redaction hook for future credential-bearing
  operations), `runner.py` (`InlineJobRunner` — synchronous, in-process,
  never imports `argparse`). New `core/application/services/jobs.py`
  wraps the runner in the `OperationResult` contract, reusing
  `OperationContext` unchanged. New `core/application/policies.py::check_can_execute_job`
  (same allowed-role set as approvals — `OPERATOR`/`APPROVER`/`ADMIN` —
  kept as a separate function since the two capabilities may diverge
  later). New `ErrorCode.UNKNOWN_OPERATION` and `ExitCode.JOB_FAILED = 7`
  (additive; `70` stays reserved exclusively for truly unexpected
  failures). CLI: `mkt jobs submit/run/list/show/cancel`.
  `demo.echo`/`demo.fail`/`demo.needs_approval` are the only registered
  operations, all `dev_only=True` — no production capability ships in
  this block.
- **Idempotency (confirmed policy):** re-running a `COMPLETED` job or
  re-cancelling a `CANCELLED` job is `ok` + warning, no re-execution, no
  new audit event. Any other non-`QUEUED` run or non-cancellable-state
  cancel is `INVALID_STATE_TRANSITION`.
- **Concurrency posture — documented, not simulated:** the
  double-execution guard is check-then-act, protecting sequential CLI
  use only, exactly like every other `Memory.v1` consumer (P-1D.3); it
  does **not** protect concurrent processes. `cancel_requested` exists on
  `JobRecord` for future non-inline runners but `InlineJobRunner` never
  reads it — a `RUNNING` job cannot be cancelled by this runner (there is
  no point in a synchronous execution where a flag could be observed),
  and the CLI/service surface that limitation as `INVALID_STATE_TRANSITION`
  with an explicit message rather than pretending to cancel.
- **Corruption tolerance — honestly scoped, not oversold:** `Memory.list()`
  bulk-reads every file for a kind in one pass with no per-file recovery
  point, so a syntactically corrupted job file fails the *whole* listing
  for that client (raises `JobPersistenceError`, never an unhandled
  traceback) rather than being silently skipped. A file that is valid
  JSON but fails the `JobRecord` schema *is* skipped per-entry, since
  that check happens after the bulk read already succeeded.
- **Notes:** 165 new tests (`tests/jobs/` — models incl. the full 6×6
  transition matrix, registry, repository, runner; `tests/application/test_jobs_service.py`;
  `tests/cli/test_cli_jobs.py`). Two bugs caught and fixed during
  implementation before they shipped: (1) `submit()` originally
  persisted the record before auditing it, so the "submitted" event's
  `event_id` never made it into the saved file — fixed by auditing
  first; (2) the FAILED-job CLI path originally printed a plain
  `"error: ..."` line onto the same stdout as the JSON payload,
  violating the clean-stdout contract — fixed by moving the diagnostic
  to stderr and keeping stdout pure JSON (the payload's own `error`
  field carries the message). Full suite green, ruff clean, approvals
  (MKT-11A/11B, 75+43 tests) and portal (52 read-only pins) re-verified
  unmodified, pipeline green, `run-campaign` untouched, ATLAS untouched.
- **Deliberately NOT done in this block:** no external queue, no
  threads, no multiprocessing, no Redis/Celery/Temporal/RabbitMQ; no
  FastAPI, no frontend; no real crawling/HTTP (that is MKT-13A per the
  master plan); no new LLM agents; `run-campaign` was not migrated onto
  jobs (that is MKT-11D); the approval model was not redesigned (that is
  MKT-12A per the master plan); no automatic publishing; no new external
  write surface. `MKT-11D — migrate run-campaign onto jobs` is the
  proposed next milestone, presented separately after this block closes.
