# Runtime — Strategy Content Backends (MKT-4A)

The strategy content backend is the swappable layer that produces the
six *creative* artifacts of the W7 workflow: value proposition,
campaign strategy, creative brief pack, social post drafts, email
sequence, reels script pack. Everything else (diagnosis, audience,
competitor benchmark, keyword plan, schedule, approval checklist,
risk assessment) stays in the deterministic templates and is **not**
routed through this layer.

- **Module:** `core/strategy/backends/`
- **CLI flag:** `mkt run-campaign --backend templated|claude` (default `templated`)
- **Default behavior:** byte-identical to MKT-3F.

## Architecture

```
PipelineOrchestrator
  └─ StrategyPipeline(strategy_backend=…)
       └─ W7TemplatedAgentBackend(strategy_backend=…)
            ├─ structural phases → core.strategy.templates.*
            └─ creative phases   → StrategyBackend.<method>(…)
                                      │
                       ┌──────────────┴──────────────┐
                       ▼                             ▼
         TemplatedStrategyBackend         ClaudeStrategyBackend
            (always succeeds)               ├─ prompts.<method>(…)
                                            ├─ ClaudeInvoker.complete(…)
                                            ├─ JSON parse
                                            ├─ Pydantic validate
                                            └─ on ANY failure →
                                               record BackendFallbackEvent
                                               and delegate to fallback
```

The Claude invoker is itself pluggable. The two invokers shipped in
MKT-4A are local-only:

- **`RefusingClaudeInvoker`** — always raises `NoRealInvokerError`.
  The CLI wires this when `--backend claude` is selected, so every
  creative call falls back and the operator sees, loudly, that no
  real Claude call happened.
- **`ScriptedClaudeInvoker`** — returns a canned string per method.
  Test-friendly.

A real invoker (Anthropic SDK, `claude` CLI subprocess, AWS Bedrock,
etc.) is **out of scope for MKT-4A** and will be added in MKT-4B
behind the same `ClaudeInvoker` interface, with no code changes
required outside the invoker module.

## Usage

### CLI

```bash
# Default — deterministic, no LLM, no fallback.
mkt run-campaign --intake examples/intake/demo-business.json

# Explicit templated (same behavior).
mkt run-campaign --intake examples/intake/demo-business.json --backend templated

# Opt-in Claude. With no real invoker wired (MKT-4A) every creative
# call falls back to templated; exit is still 0; stderr prints a
# WARNING; campaign-final-summary.md flags the situation.
mkt run-campaign --intake examples/intake/demo-business.json --backend claude
```

### Programmatic

```python
from pathlib import Path
from core.memory import JsonFileMemory
from core.pipeline import PipelineOrchestrator
from core.strategy import (
    ClaudeStrategyBackend,
    ScriptedClaudeInvoker,
)

invoker = ScriptedClaudeInvoker(responses={
    "value_proposition": '{"headline": "...", "category": "...", ...}',
    # ... canned responses for each method
})
backend = ClaudeStrategyBackend(invoker=invoker)

orch = PipelineOrchestrator(
    memory=JsonFileMemory(Path("data/clients")),
    outputs_root=Path("outputs"),
)
summary = orch.run_from_file(
    Path("examples/intake/demo-business.json"),
    strategy_backend=backend,
)

print(summary.backend_effective)        # "claude" | "mixed" | "templated"
print(summary.backend_fallback_count)   # 0..6
print(summary.backend_fallback_notes)   # ["method: ReasonType: message", ...]
```

## Fallback semantics

`ClaudeStrategyBackend` catches **three** error families and falls
back to the templated backend in each case. The original output is
never returned partially — either the LLM produces a fully valid
Pydantic instance, or the templated impl runs.

| Trigger | Recorded reason prefix |
|---------|------------------------|
| Invoker raises any subclass of `ClaudeInvokerError` (including `NoRealInvokerError`) | `ClaudeInvokerError`, `NoRealInvokerError`, ... |
| Invoker returns non-`str`, oversized payload (>256 KB), or unparseable JSON | `ClaudeOutputInvalid` |
| Parsed JSON fails Pydantic validation for the target model | `ValidationError` |

Each fallback emits **one** `BackendFallbackEvent`:

```python
@dataclass(frozen=True)
class BackendFallbackEvent:
    method: str                 # which StrategyBackend method
    requested_backend: BackendKind   # CLAUDE
    fallback_backend: BackendKind    # TEMPLATED
    reason: str                 # "ErrorType: short message" (no stack, no PII)
```

The orchestrator drains these events at the end of the strategy
stage and:

1. Emits one `audit-trail.v1` event per fallback with payload
   `{"action": "strategy_backend_fallback", "method": ..., "reason": ...}`.
2. Sets `summary.backend_fallback_count` and
   `summary.backend_fallback_notes`.
3. Computes `summary.backend_effective`:
   - `"templated"` if all 6 fell back (= effective backend is the fallback).
   - `"mixed"` if some fell back, some succeeded.
   - `"claude"` if none fell back.
4. Includes `backend_requested`, `backend_effective`,
   `backend_fallback_count` in the `started` and `finished` audit
   events.
5. `render_markdown_summary` adds a "Strategy backend" section that
   shows each fallback and, when no real Claude call happened,
   says so explicitly.

## Safety boundaries

The Claude backend layer never:

- Imports `anthropic` or any other LLM SDK.
- Opens a network socket.
- Reads or writes outside the tenant scope already enforced by the
  memory layer.
- Reads environment variables, `.env` files, or credentials.
- Spawns subprocesses.
- Executes shell commands.
- Includes URLs, emails, phone numbers or credentials in prompts
  beyond what the input brief already contains.
- Echoes raw model output into audit events or summaries (only
  short, sanitised `ErrorType: message` strings).

The `ClaudeInvoker` interface is the *only* extension point at
which any of the above could happen. Until a real invoker is wired
(MKT-4B) every invocation that asks for Claude falls back to the
deterministic templated backend.

## Guarantees preserved

- **Pydantic validation on every output** — whether the output
  came from the templated impl or the LLM, the value returned to
  the W7 layer is a fully validated Pydantic instance.
- **Claim Audit always runs** — MKT-3B's claim audit is unchanged
  and processes every output regardless of backend.
- **Approval Pack still blocks** — `blocks_publish` semantics are
  unchanged. `--require-approval` and `--stop-on-blocked` work
  exactly the same with Claude as with templated.
- **Determinism preserved when default** — without
  `--backend claude`, output is byte-identical to MKT-3F.

## Exit codes (CLI)

Unchanged from MKT-3F. `--backend claude` with no real invoker
still exits 0 (the pipeline completed correctly via fallback).
Operators who want non-zero on any fallback can grep stderr for
the `WARNING:` line, or check `backend_fallback_count > 0` in
the JSON payload printed to stdout.

## Validation

- 31 new tests in `tests/strategy/backends/`.
- 6 new CLI tests in `tests/cli/test_cli_backend_flag.py`.
- 9 new orchestrator tests in
  `tests/pipeline/test_orchestrator_backend.py`.
- Full suite green (829 tests).
- `ruff check .` clean.
