# ADR 0007 — MKT-2B: Agent/Skill Contracts + Backend Interface

- **Status:** Accepted
- **Date:** 2026-05-29
- **Block:** MKT-2B
- **Supersedes:** —
- **Contracts:** `agent-spec.v1`, `skill-spec.v1` (both new, Pydantic).
- **Resolves:** P-2A.2 (full), P-2A.7 (full). Updates P-2A.3 (still
  scaffolding-only) and P-1E.1 (now complete: workflow + agent + skill all
  Pydantic).

## Context

MKT-2A landed the minimal dispatcher with a mock agent and a single
predicate kind. Two questions remained before any real agent could be
spawned:

1. What does the system know about an agent / skill at load time? (Today
   the linter parses frontmatter and Pydantic-validates nothing about it
   beyond a key-present check.)
2. What is the swap point for a real agent backend? (Today `MockAgent` is
   hardcoded; future swaps would touch every importer.)

This block answers both without invoking Claude Code.

## Decision

### D-7.1 — `agent-spec.v1` and `skill-spec.v1` live in `core/agents/` and `core/skills/`

Following ADR 0006 D-6.1: specs are loaded artifacts, not transport
contracts. They go next to their loaders, not in `core/contracts/`.

### D-7.2 — IO entries are tolerant by design

The 16 agent specs and 17 skill specs written in MKT-1E use minor format
variations (`{kind: brief, required: true}` in agents, `{sample_texts:
list[str]}` in skills, sometimes bare strings). Tight schemas would
require rewriting 33 specs. Instead:

- `AgentIOEntry` (`core/agents/spec.py`) uses `extra="allow"` with `kind`
  and `required` as recognized fields. Any extra key is preserved.
- `SkillSpec.inputs` and `SkillSpec.outputs` are `list[Any]` validated
  only to be `dict | str` per entry.

The top-level models (`AgentSpec`, `SkillSpec`) retain `extra="forbid"`
to catch top-level typos. The trade is between completeness and not
breaking existing work.

### D-7.3 — `AgentBackend` is an ABC

Mirrors the choice for `Memory` (ADR 0004 D-4.1). Explicit > duck typed
when we want subclasses to be caught at construction time, not at runtime.

### D-7.4 — `AgentInvocation` is a small frozen dataclass

Carries `agent_id`, `phase_id`, `workflow_id`, `client_slug`. The minimal
set the dispatcher needs to identify "what is being run for whom".

Future fields (read-only memory view, resolved upstream entities, spec
view) are added per block, not speculatively up front.

### D-7.5 — `ClaudeCodeBackend` is scaffolding, not a stub

Same pattern as `EngramMemory` (ADR 0004 D-4.6):

- Same module path.
- Same constructor that accepts any args silently.
- Every method raises `NotImplementedError` with a pointer to the safety
  doc and a directive to use `MockAgentBackend`.
- NO import of Anthropic SDK, no MCP client, no shell-out to `claude`
  CLI.

The point is to make the import surface stable so dependent code can be
written today.

### D-7.6 — Promotion of `ClaudeCodeBackend` is gated by `docs/runtime/agent-backend-safety.md`

The safety doc enumerates 8 non-negotiable guarantees that any real
backend must satisfy (filesystem allowlist, network allowlist, tool
restriction, env scrubbing, budgets, audit-on-spawn, compliance
isolation, reproducibility). The promotion block MUST tick every box
before merging.

This is recorded here, not only in the safety doc, so a future reviewer
sees the promotion path is intentional and irrevocable except by another
ADR.

### D-7.7 — `predicates.evaluate_required_gate` is the dispatcher's choke point

Today's policy is unchanged from MKT-2A: a gate is held iff a prior phase
declared it produced. The change is structural — the dispatcher no longer
inlines `gate in held_gates`; it calls
`predicates.evaluate_required_gate(state, gate_name)`.

The reason is single-place-of-change. Future blocks (e.g. one that
implements `no_unsafe_claims` as a re-scan over envelopes) extend this
function without touching the dispatcher.

### D-7.8 — `status_equals` joins `envelope_present` in the predicate registry

Both are useful and cheap. `status_equals` pairs with `PASS`/`FAIL`
validator agents (claim-validator, future QA agents). The remaining 5
kinds (`claims_audit_present`, `no_unsafe_claims`, `memory_key_exists`,
`artifact_exists`, `custom`) continue to raise `UnknownPredicate`.

### D-7.9 — `MockAgent` and `MockAgentInput` are removed; `MockAgentBackend` and `AgentInvocation` replace them

There is one source of truth for the mock backend, in
`core/runtime/backends/mock.py`. The old `core/runtime/mock_agent.py` is
deleted. Tests are updated. No back-compat shim — the API is internal.

### D-7.10 — `default_model` enum is `opus | sonnet | haiku`

Other values rejected at spec load. The 16 specs in MKT-1E only use
`opus` and `sonnet`; `haiku` is allowed for future low-stakes utility
agents.

This is binding at the spec level: a runtime override (e.g. dispatcher
policy chooses to send a `sonnet`-spec'd agent to `opus` for a one-off
investigation) is a separate concern.

### D-7.11 — `deterministic` field accepts `bool` or the literal `"partial"`

In the v1 specs, `approval-packager` is marked `deterministic: partial`
(it's deterministic given the artifact hashes, less so given metadata
timing). The Pydantic field type is `bool | Literal["partial"]`.

### D-7.12 — Linter delegates Pydantic validation to the loaders

`lint_agent_file` and `lint_skill_file` now call `load_agent` / `load_skill`
and surface validation failures as single `agent_invalid` / `skill_invalid`
findings. The previous rule-specific findings
(`agent_missing_field`, `agent_invalid_status`, etc.) collapse into the
unified rule. Cross-spec checks (e.g. `agent_skill_not_found`) remain.

## Alternatives considered

- **Put `agent-spec.v1` in `core/contracts/`.** Rejected — same reason as
  workflow-spec (D-6.1, this is loaded artifact, not transport).
- **Reject minor format variations and force a rewrite of 33 specs.**
  Rejected — wasted churn for marginal gain.
- **Make `AgentBackend` a Protocol.** Rejected (D-7.3).
- **Keep `MockAgent` as an alias for backward compat.** Rejected (D-7.9)
  — API is internal, one source of truth wins.
- **Build a tiny mocked Claude Code spawn ("simulate the API surface")
  instead of raising NotImplementedError.** Rejected — invites callers
  to depend on shape that doesn't exist yet.
- **Promote `default_model` to a full enum table with model IDs**
  (`claude-opus-4-7-20260301` etc.). Rejected — coupling the spec to a
  specific model id is the wrong layer; the runtime resolves the family
  to a concrete id.

## Consequences

- The dispatcher is one constructor call away from a real backend.
- The spec linter now catches every malformed agent / skill spec, not
  just missing fields.
- The 16 agent + 17 skill specs are validated by tests on every run.
- The Approval Center work (P-1E.5) can refer to `agent-spec.v1` when
  defining who approves what.
- The promotion of `ClaudeCodeBackend` has an explicit, documented
  checklist. Nobody can "casually" enable real spawn.

## Out of scope for MKT-2B

- Real Claude Code subagent spawn (gated by safety doc).
- Anthropic SDK backend (same gate).
- Parallel agents within a phase.
- Retry / resume.
- New predicate evaluators beyond `status_equals` (next ones land with
  the blocks that need them).
- Migration of stored entities to new spec versions.
- CLI surface beyond what MKT-2A shipped (no new subcommands).
