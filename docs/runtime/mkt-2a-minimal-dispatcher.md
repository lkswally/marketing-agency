# MKT-2A — Minimal Dispatcher

> Status: **implemented** (MKT-2A).
> Module: `core.runtime`.
> Backend: `core.memory.JsonFileMemory`.
> Agent: `core.runtime.MockAgent` (only — Claude Code spawn is MKT-2B+).

The minimal dispatcher is the smallest viable runtime that exercises every
contract end to end: workflow spec → phase iteration → mock envelope →
strict validation → memory write → audit trail.

It is mock-only by design. Promotion to Claude Code subagent spawns is a
separate block with its own approval.

---

## 1. What it does

1. Loads a `WorkflowSpec` (validated against `workflow-spec.v1`).
2. Generates a `run_id` and emits a `workflow_started` audit event.
3. For each phase in declaration order:
   - Checks that every `gates_required_before` value is held by the run state.
     If any are missing, the run fails immediately with `GateBlockingError`.
   - For each agent listed in the phase, invokes `MockAgent.run(...)` which
     returns a deterministic, valid `ReturnEnvelope`.
   - Re-validates the envelope with `validate_envelope_strict` (defense in
     depth — the contract is the only source of truth).
   - Persists the envelope to `JsonFileMemory` under
     `kind=envelope, entity_id=<uuid>`.
   - Emits an `envelope_received` audit event.
   - Marks every `gates_produced` value as held in the run state.
4. Builds a `WorkflowRunSummary` with full step history and persists it
   under `kind=workflow_run, entity_id=<run_id>`.
5. Emits a `workflow_finished` audit event.

The audit chain is verified-by-construction: every event's `prev_hash`
matches the previous event's `hash` (enforced by `Memory.append_audit_event`).

## 2. What it does NOT do

- **No Claude Code spawn.** The agent is `MockAgent`, period.
- **No parallel phases.** Agents within a phase run sequentially.
- **No retry.** A failure halts the run.
- **No approval handoff.** Approval Center wiring is a separate block.
- **No `claims_audit` enforcement.** Compliance is MKT-3.
- **No predicate kinds other than `envelope_present`.** Other kinds raise
  `UnknownPredicate` if requested (the dispatcher in MKT-2A does not yet
  consult the predicate registry directly — it short-circuits to the
  in-memory `held_gates` set; the registry is in place for MKT-2B).

## 3. CLI surface

The `mkt` console script (installed via `pip install -e .`):

```
mkt list-workflows [--workflows-dir DIR]
mkt validate-specs [--workflows-dir DIR --agents-dir DIR --skills-dir DIR]
mkt memory inspect [--client SLUG] [--root DIR]
mkt run-mock WORKFLOW_ID --client SLUG [--workflows-dir DIR --root DIR]
```

Defaults assume the CWD is the repo root:
- `--workflows-dir` → `workflows/`
- `--agents-dir` → `agents/`
- `--skills-dir` → `skills/`
- `--root` → `data/clients/`

### Examples

```bash
# What workflows are defined?
mkt list-workflows

# Are all specs valid?
mkt validate-specs

# What state has been persisted?
mkt memory inspect --client default

# Run W1 end-to-end with a mock agent.
mkt run-mock W1_intake_to_strategy --client default
```

The last command prints the `WorkflowRunSummary` as JSON and exits 0 on
success. It writes:

```
data/clients/default/
├── _meta.json
├── envelope/         # one JSON per emitted envelope
│   └── <uuid>.json
├── workflow_run/
│   └── <run_id>.json
└── audit/
    ├── YYYY-MM-DD.jsonl
    └── _chain_tail.txt
```

## 4. Architecture

### Core types

| Type | Purpose |
|------|---------|
| `WorkflowSpec`, `PhaseSpec`, `ApprovalSpec` | Pydantic models for `workflow-spec.v1`. |
| `MinimalDispatcher` | The executor. Stateless across runs (state lives in `RunState`). |
| `RunState` | Per-run in-memory bookkeeping: envelopes, held gates, step history. |
| `MockAgent`, `MockAgentInput` | Deterministic envelope producer. |
| `LintFinding` + `lint_*` | Spec linter — pure, read-only. |

### Memory kinds introduced

| Kind | Lifecycle | Notes |
|------|-----------|-------|
| `envelope` | Per envelope emitted in a run. | Carries a `__envelope_id` metadata key (prefixed `__` to signal "runtime, not domain"). |
| `workflow_run` | One per run. | Persisted as `WorkflowRunSummary.model_dump()`. |

Neither is a `core.domain` entity; both are runtime artifacts. If you need
typed access, dump-then-validate via the matching contract model.

### Audit events emitted

| Event type | When | Payload |
|------------|------|---------|
| `workflow_started` | First action of the run. | `{run_id, workflow_id, workflow_version}` |
| `envelope_received` | After each successful agent envelope. | `{run_id, envelope_id, agent, status}` |
| `workflow_finished` | Last action of the run. | `{run_id, status, envelope_count}` |

## 5. Spec linter

`core.workflows.lint_all(...)` aggregates findings from three smaller
linters:

| Linter | Checks |
|--------|--------|
| `lint_workflow_spec` | Every `agents[]` exists under `agents/`; warns when a consumed gate is also produced by the same workflow but at a later phase (likely intra-workflow ordering bug). Cross-workflow gates are NOT flagged. |
| `lint_agent_file` | Frontmatter present; required keys (`agent_id`, `version`, `spec_version`, `status`) present; `status` is `spec_only` or `implemented`; referenced `skills[]` exist under `skills/`. |
| `lint_skill_file` | Frontmatter present; required keys (`skill_id`, `version`, `spec_version`, `status`) present; `status` is one of the allowed values. |

Findings carry a `severity` (`error` / `warning`) and a stable `rule` id.
The CLI uses `len(errors)` as the exit code (0 / 1).

## 6. What the dispatcher rejects

Failure modes that surface as `WorkflowRunStatus.FAILED`:

- A required gate is not held when a phase starts.
- Any agent's mock envelope fails strict validation (this is a regression
  trap — `MockAgent` always emits a valid envelope).

Failure modes that raise (caller-visible exceptions):

- `WorkflowLoadError` if the YAML is malformed or the schema is violated.
- `UnknownPredicate` if a workflow references a predicate kind the
  dispatcher does not evaluate yet.

## 7. Out of scope (and where it goes)

| Concern | Block |
|---------|-------|
| Claude Code subagent spawn | MKT-2B |
| Approval Center wiring | MKT-2B / MKT-2C |
| Compliance enforcement (`claim_strict`) | MKT-3A / MKT-3B |
| Remaining `predicate_kind` evaluators | per block |
| Retry / resume | MKT-2C |
| Parallel agents within a phase | MKT-2B |
| `mkt memory put` / `mkt memory tail-audit` | optional CLI extensions |
