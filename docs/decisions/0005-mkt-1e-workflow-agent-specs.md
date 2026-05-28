# ADR 0005 — MKT-1E: Workflow + Agent + Skill Specs (Documentation-only Block)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Block:** MKT-1E
- **Supersedes:** —
- **Contracts:** none introduced in code; spec formats `workflow-spec.v1`,
  `agent-spec.v1`, `skill-spec.v1` are documented (markdown + YAML).

## Context

MKT-1B through MKT-1D delivered the bones: domain model, operational
contracts, storage layer. Before any dispatcher (MKT-2A) gets built, we want
the workflows, agents, and skills the system must support to be **named,
shaped, and reviewed**.

Writing the runtime against an undocumented mental model is how the system
becomes a sprawl of one-off scripts. This block answers, on paper, what the
agency does end to end.

## Decision

### D-5.1 — Specs as declarative files, not Pydantic contracts (yet)

YAML for workflows, Markdown-with-frontmatter for agents and skills.
**Not** introduced as `workflow-spec.v1` / `agent-spec.v1` / `skill-spec.v1`
Pydantic contracts in MKT-1E.

Promotion to versioned Pydantic contracts happens in MKT-2A, when the
dispatcher needs to validate them on load. Until then, the schemas live in
`docs/workflows/overview.md` (and the file shapes themselves serve as
"by example" templates).

Rationale: the right shape for the contracts will reveal itself when the
first runtime tries to consume them. Locking the contracts now risks
specifying the wrong fields.

### D-5.2 — Every agent and skill has `status: spec_only`

The field is mandatory in frontmatter. The future dispatcher MUST refuse to
spawn an agent (or invoke a skill) whose status is not `implemented`.

Promotion to `implemented` is a per-spec change in its own commit, with
tests. This makes the "is this thing real?" question answerable by reading
the file.

### D-5.3 — Approval Center is documented as a fixed state machine

`PROPOSED → IN_REVIEW → APPROVED | REJECTED | NEEDS_REVISION → IN_REVIEW`.
Documented in `docs/approval-center.md`. Implementation deferred.

Rationale: approval state drift is the easiest path to compliance debt.
Fixing the states up front prevents the implementation from inventing new
ones casually.

### D-5.4 — n8n stays external; MKT plans, n8n executes

MKT produces `n8n_plan` entities. A human or a far-future export skill
translates them into n8n workflows. The core never imports an n8n client;
when it does (R3 in `n8n-automation-roadmap.md`), it does so via an
opt-in bridge adapter (`MKT_BRIDGE_N8N=0` default).

Rationale: n8n already does scheduling and recurring workflow execution
better than anything we'd reimplement. Coupling the core to it would
violate the standalone guarantee (ARCHITECTURE.md D2).

### D-5.5 — Portal lives outside the core, deferred

`docs/portal-roadmap.md` describes views and phases. No `apps/portal/` is
created. When the Portal lands, it consumes Memory through a read-only API
defined at that time.

Rationale: a UI choice (Next, SvelteKit, Astro, plain HTML) is the wrong
decision to bind today. The core must keep working without a portal.

### D-5.6 — Phase-gate naming convention `g_<noun>_<verb_past>`

Pinned in `docs/workflows/overview.md` §3. Examples: `g_brief_captured`,
`g_audience_research_complete`, `g_compliance_passed`, `g_approval_granted`.

Rationale: convention prevents Babel. A reader can predict the gate name
without looking it up.

### D-5.7 — Skills are atomic; agents compose

A skill does NOT call another skill. An agent owns composition. This keeps
skill specs short, replaceable, and testable in isolation.

Rationale: the moment skills can call skills, dependency graphs appear.
Agents are the right level for orchestration.

### D-5.8 — Approval states fixed

`PROPOSED, IN_REVIEW, APPROVED, REJECTED, NEEDS_REVISION`. No `PENDING`,
no `DRAFT`. Adding a state is breaking and must be a separate ADR.

### D-5.9 — `human_required_at` is the only knob workflows use to opt into approval

A workflow does NOT decide its own approval state machine. It only declares
which phase requires human action. The Approval Center owns the rest.

Conservative defaults: human required at strategy (W1), assemble (W3),
approval (W5). No human in research, drafts, or reporting.

### D-5.10 — Specs are markdown + YAML, parseable by any tool

Frontmatter YAML up top, prose below. A linter, the future dispatcher, or
the portal can all parse the same files without touching Python.

### D-5.11 — One workflow per file, one agent per file, one skill per file

No aggregation (`agents/all.md`, `skills.yaml`). Per-file granularity makes
diffs small, blame attributable, and additions cheap.

### D-5.12 — Cross-spec references are by id, not by file path

Workflows reference agents by `agent_id`, agents reference skills by
`skill_id`. The id alphabet is `[a-z][a-z0-9-]*`.

Rationale: file paths could change (e.g. moving `agents/` to
`packages/agents/`); ids should not.

### D-5.13 — Risks and limits are mandatory frontmatter fields

Every agent declares at least one risk and one limit. Reasons:
1. Forces the spec author to think about failure modes.
2. Future compliance / observability layers can read them directly.

Empty lists are allowed only if the author writes a comment explaining
why.

## Alternatives considered

- **Specs in YAML only** (no Markdown). Rejected: prose explains *why*; YAML
  alone is hostile to reviewers and to future portal rendering.
- **Single mega-file** with all specs. Rejected for diff and review hygiene
  (D-5.11).
- **Promote spec formats to Pydantic contracts now.** Rejected: premature
  (D-5.1).
- **Embed approval state machine inside each workflow.** Rejected: drift
  guarantee. The state machine belongs to the Approval Center, not to
  individual workflows (D-5.3).
- **Skills call skills (DAG).** Rejected: explodes complexity at the wrong
  layer (D-5.7).

## Consequences

- A future dispatcher (MKT-2A) has a complete, deduplicated map of what to
  run.
- Reviewers can audit the "is the agency complete?" question without
  reading code.
- The Portal team (when one exists) can render specs directly.
- Promoting to Pydantic contracts later is straightforward — the YAML
  already matches the eventual shape.

## Out of scope for MKT-1E

- Any runtime / dispatcher / CLI.
- Pydantic contracts for the spec formats.
- Real n8n connection.
- Real portal / landing.
- Real analytics connectors.
- Tests for the specs themselves (would require a linter; deferred to
  MKT-2A).
