# ADR 0006 — MKT-2A: Minimal Dispatcher + Spec Linter + CLI

- **Status:** Accepted
- **Date:** 2026-05-28
- **Block:** MKT-2A
- **Supersedes:** —
- **Contracts:** `workflow-spec.v1` (Pydantic, new).
- **Resolves:** P-1C.2 (partial), P-1C.3 (partial), P-1D.5, P-1E.1, P-1E.2.

## Context

MKT-1B–1D delivered the bones; MKT-1E declared what runs on top. The
question was: what is the smallest runtime that proves the contracts hold
together end to end without committing to Claude Code spawn or external
services?

This block answers it with a mock-only, sequential, single-process
dispatcher that can be inspected, tested, and reverted cheaply.

## Decision

### D-6.1 — `workflow-spec.v1` lives in `core/workflows/`, not `core/contracts/`

`core/contracts/` holds **transport** contracts (envelope, audit event,
phase gate, claim audit, workflow run summary). A workflow spec is a
**loaded artifact** — closer to a config file than to a wire format. Putting
it next to `loader.py` and `linter.py` keeps the cognitive distance small.

The `spec_version` discipline is preserved (`workflow-spec.v1` pinned via
`Literal`).

### D-6.2 — The dispatcher is minimal by design

One predicate kind evaluated (`envelope_present`), sequential phases,
sequential agents within a phase, no retry, no approval handoff. Anything
beyond that lives in MKT-2B+.

Rationale: a smaller surface produces a stronger guarantee. Every behavior
the dispatcher exhibits today is testable in isolation. Expanding the
surface block by block keeps the cost of each expansion bounded.

### D-6.3 — Agent runtime is `MockAgent` only

The dispatcher accepts an injectable agent (`MinimalDispatcher(..., agent=...)`).
The default and only implementation in MKT-2A is `MockAgent`, which
produces a deterministic, valid `ReturnEnvelope` for any agent_id / phase
pair.

Promotion to Claude Code subagent spawns is a separate block. The
`MockAgent` is permanent: future blocks should use it for tests even after
real spawn exists.

### D-6.4 — Two new memory kinds: `envelope`, `workflow_run`

Both are runtime artifacts, not domain entities. They live in Memory
because the dispatcher needs them durable for inspection and for
`envelope_present` evaluation across phases (which only consults in-memory
state today, but storage parity matters for resume — future).

The `envelope` payload carries a `__envelope_id` field prefixed with `__`
to signal "runtime metadata, not part of `envelope.v1`". Strict re-validation
strips it.

### D-6.5 — Audit chain is built by construction

The dispatcher never calls `compute_event_hash` directly. Every event is
constructed via `AuditTrailEvent.build(...)` with `prev_hash =
memory.last_audit_hash(client_slug)`. The chain is therefore always valid
by virtue of the storage layer's invariants — there is no second-source-of-
truth for the hash.

### D-6.6 — Spec linter is pure and file-system-read-only

`lint_all` walks `workflows/`, `agents/`, `skills/` and aggregates
`LintFinding` records. It writes nothing. The CLI exits 1 iff any finding
is an `error`; warnings do not block.

Rationale: linting in CI should be cheap and idempotent. Side effects in a
linter are how lint becomes feared.

### D-6.7 — CLI uses stdlib `argparse`, no external lib

Four subcommands × one process × no interactivity = `argparse` is more than
enough. Adding `click` or `typer` would be a dependency surface paid for
nothing measurable.

### D-6.8 — CLI installs as `mkt` via `[project.scripts]`

`pip install -e .[dev]` exposes `mkt --help`. The entry point is
`cli.main:main`. The function takes an optional `argv` for testability and
an optional `out` stream so tests can capture output without monkeypatching
`sys.stdout`.

### D-6.9 — `pyyaml` is the only new runtime dependency

The workflows live in YAML by approved decision (MKT-1E). A hand-rolled
parser would be fragile; converting to JSON would walk back a UX choice
already made. `pyyaml` is the de-facto standard with no transitive deps.

### D-6.10 — `mkt run-mock` requires `--client` explicitly

There is no implicit default client. The flag prevents accidental writes
to a "default" tenant when the user meant something specific. The cost is
one extra typed argument; the benefit is "did you mean to write here?"
becoming impossible to forget.

### D-6.11 — Spec-version `workflow-spec.v1` is now a versioned contract

Promoted from prose (MKT-1E) to Pydantic (MKT-2A). Breaking changes bump
to `workflow-spec.v2` with a new module and a migration plan for stored
specs. Additive changes (new optional fields) stay within v1.

`agent-spec.v1` and `skill-spec.v1` are NOT promoted in this block —
the linter checks the frontmatter shape without binding it to Pydantic.
Promotion happens when the runtime starts spawning real agents (MKT-2B+).

### D-6.12 — Failure mode of a missing required gate is `WorkflowRunStatus.FAILED`

The dispatcher records a synthetic `StepResult` carrying the blockers, then
finalizes the run as `FAILED`. No exception bubbles out to the caller — the
summary IS the report.

Rationale: the dispatcher is intended to be a building block other code
calls. Raising on gate failure would force every caller to wrap it. The
summary is enough.

## Alternatives considered

- **`workflow-spec.v1` in `core/contracts/`.** Rejected (D-6.1) — wrong
  neighborhood.
- **Stream-of-events dispatcher (each step is a generator).** Rejected for
  v1 — over-engineered for sequential, single-process, mock-only execution.
- **Click-based CLI.** Rejected (D-6.7) — gains do not justify the dep.
- **Make `mkt run-mock` accept a default client.** Rejected (D-6.10) — the
  implicit default is exactly what we want to make impossible.
- **Persist `WorkflowRunSummary` inside the audit JSONL.** Rejected — the
  audit trail is for events, not for arbitrary artifacts. Summaries belong
  in their own kind.

## Consequences

- The system can now be exercised end to end: load → validate → dispatch
  → memory → audit, with deterministic output.
- Future blocks add to the surface (Claude Code spawn, new predicate kinds,
  retry, approval) without touching the validated core.
- CI can run `mkt validate-specs` as a cheap, fast check.
- Anyone reading the repo can run `mkt run-mock W1 --client default` and
  see a complete trail of what the system would do.

## Out of scope for MKT-2A

- Claude Code subagent spawn (MKT-2B).
- Approval Center wiring (MKT-2B / MKT-2C).
- Compliance enforcement (MKT-3A / MKT-3B).
- `status_equals` / `claims_audit_present` / `no_unsafe_claims` /
  `memory_key_exists` / `artifact_exists` / `custom` predicate evaluators.
- `qa_strict` / `dev_strict` / `design_strict` / `claim_strict` envelope
  modes.
- Parallel agents within a phase.
- Retry / resume.
- Live agent or skill execution (everything is mocked).
- Real connectors of any kind (GA4, Resend, n8n, social).
