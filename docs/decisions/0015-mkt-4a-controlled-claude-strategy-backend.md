# ADR 0015 — MKT-4A: Controlled Claude Strategy Backend

- **Status:** Accepted
- **Date:** 2026-05-31
- **Block:** MKT-4A
- **Supersedes:** —
- **Contracts touched:** `pipeline-run.v1` (additive fields,
  backward-compatible).

## Context

After MKT-3F the agency operating system ran end to end on a single
command, but every artifact (strategy, copies, emails, reels,
creative briefs) was produced by deterministic templates. Templates
give us reviewability, determinism and zero external dependency, but
they are also limited: they don't surprise, don't pun, don't pick
the right idiom for a specific industry.

MKT-4A introduces the infrastructure for LLM-backed content
generation while preserving every cardinal guarantee the
deterministic pipeline established:

- The system must keep working without any LLM.
- A bad LLM output must never reach a deliverable.
- The Claim Audit must still run on every claim regardless of
  origin.
- The Approval Pack must still gate publish.
- Operators must always be able to tell which backend produced
  what.

## Decision

### D-15.1 — Pluggable content backend, not a workflow rewrite

A new `StrategyBackend` ABC (in `core/strategy/backends/`) exposes
six methods, one per creative artifact:

| Method                    | Returns                       |
|---------------------------|-------------------------------|
| `value_proposition`       | `ValueProposition`            |
| `campaign_strategy`       | `CampaignStrategy`            |
| `creative_brief_pack`     | `CreativeBriefPack`           |
| `social_post_drafts`      | `list[SocialPostDraft]`       |
| `email_sequence`          | `EmailSequenceDraft`          |
| `reels_script_pack`       | `ReelsScriptPack`             |

The W7 strategy `AgentBackend` (renamed
`TemplatedStrategyBackend` → `W7TemplatedAgentBackend` to clear
the namespace) routes the corresponding W7 phases through the
injected `StrategyBackend`. Structural phases (intake, diagnose,
audience, competitor, channels, keywords, calendar, approval,
report) still call `core.strategy.templates.*` directly.

Two implementations ship:

- `TemplatedStrategyBackend` — wraps `templates.*`. Default. Never
  falls back (it IS the fallback). Output is byte-identical to MKT-3F.
- `ClaudeStrategyBackend` — uses prompts + a pluggable
  `ClaudeInvoker` + Pydantic validation + automatic fallback.

### D-15.2 — `ClaudeInvoker` is the single LLM extension point

The Claude backend never talks to an LLM directly. It calls
`invoker.complete(prompt, system=..., context=...)` and the invoker
is responsible for whatever happens next. The interface is
deliberately minimal — no streaming, no tool use, no multi-turn —
because in MKT-4A the only invokers shipped are:

- `RefusingClaudeInvoker` — always raises `NoRealInvokerError`.
  The CLI wires this when `--backend claude` is requested.
- `ScriptedClaudeInvoker` — returns canned strings keyed by
  method. Test-only.

The real invoker (Anthropic SDK / `claude` CLI subprocess /
Bedrock / ...) is explicitly **out of scope for MKT-4A** and
moves to **MKT-4B**. That separation lets MKT-4A be reviewed,
shipped and tested without ever touching credentials, network or
SDKs.

### D-15.3 — Fallback is automatic, observable, and never silent

`ClaudeStrategyBackend` catches three families of failure and
falls back to the templated backend:

1. The invoker raises any subclass of `ClaudeInvokerError`.
2. The invoker returns a non-`str`, a payload larger than 256 KB,
   or text that does not parse as JSON.
3. The parsed JSON fails Pydantic validation for the target
   model.

Each fallback emits one `BackendFallbackEvent` with:

- the method that fell back,
- the requested backend (always `CLAUDE` in MKT-4A),
- the fallback backend (always `TEMPLATED` in MKT-4A),
- a short, sanitised reason of the form `"ErrorType: message"`
  (no stack traces, no secrets, no raw model output).

The orchestrator surfaces these events in three places:

1. **Audit trail** — one `audit-trail.v1` event per fallback with
   `payload.campaign_pipeline.action == "strategy_backend_fallback"`,
   plus the requested/effective backend in the `started` and
   `finished` events. The hash chain remains valid.
2. **`campaign-final-summary.md`** — a "Strategy backend" section
   shows the requested vs effective backend, lists every fallback,
   and explicitly states "NINGUNA llamada creativa fue resuelta
   por Claude real" when all six fell back.
3. **CLI stderr** — a single `WARNING:` line when
   `backend_requested == "claude"` and `fallback_count > 0`.

The CLI exit is still 0 because the pipeline completed correctly.
An operator who wants non-zero on fallback can:
- grep stderr for `^WARNING:`, or
- inspect `backend_fallback_count` in the JSON payload printed
  to stdout, or
- read `summary.backend_fallback_count` from memory.

### D-15.4 — `backend_effective` summarises what really happened

`CampaignRunSummary` adds four additive fields (backward-compatible
because they all have defaults):

| Field | Type | Values |
|-------|------|--------|
| `backend_requested` | `Literal["templated","claude"]` | what the operator asked for |
| `backend_effective` | `Literal["templated","claude","mixed"]` | what actually ran the creative methods |
| `backend_fallback_count` | `int >= 0` | how many of the six methods fell back |
| `backend_fallback_notes` | `list[str]` | short `"method: reason"` strings |

`backend_effective` is computed as:

- `templated` if `backend_requested == "templated"`, OR if all six
  methods fell back.
- `claude` if `backend_requested == "claude"` and zero fell back.
- `mixed` if `backend_requested == "claude"` and at least one but
  not all six fell back.

### D-15.5 — Default is templated; nothing changes without an opt-in

`mkt run-campaign` without `--backend` keeps the MKT-3F behavior.
The orchestrator's `strategy_backend` kwarg defaults to `None`
and the W7 layer falls through to a fresh `TemplatedStrategyBackend()`.
Existing MKT-3A → MKT-3F tests all pass unchanged.

### D-15.6 — Safety boundaries are *in the interface*, not just policy

The `ClaudeInvocationContext` passed to every invoker call contains
**only** the method name, the tenant slug, and per-call generation
limits (`max_tokens`, `temperature`). It does **not** carry
filesystem paths, environment variables, credentials, network
endpoints, or tools. The invoker can do whatever a future MKT-4B
implementation needs to do, but it has to do it without help from
the orchestrator's state. That makes auditing a future invoker a
single-file review.

The `ClaudeStrategyBackend` itself imports no SDK, opens no
socket, reads no env var, and writes nothing to disk that the
fallback wouldn't write.

## Consequences

### Positive

- Adds an LLM hook without changing the deterministic default.
- Every cardinal guarantee (Pydantic validation, Claim Audit,
  Approval Pack blocking, audit chain) remains intact.
- The system stays operable even when a real Claude invoker is
  added and starts failing intermittently — every error path
  collapses to the templated backend.
- Operators can audit which methods came from Claude vs templates
  per run, from memory, from the markdown summary, from stderr,
  or from the audit trail.

### Negative / accepted trade-offs

- The prompts in `backends/prompts.py` are conservative: they list
  field names, types, and length bounds inline. A future block can
  replace them with JSON-schema-driven prompts, but the current
  shape is enough to validate the wiring.
- The Claude backend has no streaming, no tool use, no multi-turn
  conversation, no retries. A real invoker that wants those will
  build them inside the `complete(...)` call, not by widening the
  interface.
- `ClaudeOutputInvalid` and `ClaudeInvokerError` use `RuntimeError`
  ancestry plus a `# noqa: N818` for the missing `Error` suffix.
  Same trade-off as in MKT-3F's typed sentinels — chosen for
  brevity and consistency with the rest of the codebase.
- `backend_effective == "templated"` when `backend_requested ==
  "claude"` and all six methods fall back. This is correct but
  potentially surprising. The renderer says "NINGUNA llamada
  creativa fue resuelta por Claude real" to remove all ambiguity.

## Out of scope (explicit)

The following are **not** done in MKT-4A:

- No Anthropic SDK import.
- No `claude` CLI subprocess.
- No network of any kind.
- No credentials, no env var reads.
- No MCP, no n8n, no GA4, no Google Ads.
- No real image generation, no publishing, no email.
- No new HTTP endpoints, no new file writes outside the existing
  tenant scope.
- No retries, no backoff, no streaming, no tool use, no multi-turn.
- No prompt versioning / per-tenant prompt overrides.
- No cost tracking, no token counters (the invoker is responsible
  if MKT-4B wants them).

All of the above are tracked in `PENDING.md` under `P-4A.*` and
`P-4B.*`.

## Validation

- 31 new tests in `tests/strategy/backends/`:
  - 6 invoker tests
  - 9 templated backend tests
  - 6 Claude happy-path tests
  - 10 Claude fallback / safety tests
- 6 new CLI tests in `tests/cli/test_cli_backend_flag.py`.
- 9 new orchestrator tests in
  `tests/pipeline/test_orchestrator_backend.py`.
- Full test suite: **829 passed**.
- Ruff: **clean**.
- ATLAS core (sibling repo): untouched.

## Related

- Builds on MKT-3F (pipeline orchestrator) and MKT-3A (W7 strategy
  engine).
- Real `ClaudeInvoker` implementation moves to **MKT-4B**.
- Cross-link: `docs/runtime/strategy-backends.md` (operator guide)
  and `docs/runtime/agent-backend-safety.md` (policy).
