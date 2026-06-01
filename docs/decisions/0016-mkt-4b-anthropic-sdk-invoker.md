# ADR 0016 — MKT-4B: Anthropic SDK Invoker

- **Status:** Accepted
- **Date:** 2026-06-01
- **Block:** MKT-4B
- **Supersedes:** —
- **Contract:** extends `pipeline-run.v1` with the additive field
  `claude_invocations: list[ClaudeInvocationRecord]`. No version bump.

## Context

MKT-4A landed the full Claude-backend scaffolding (StrategyBackend
ABC, ClaudeStrategyBackend, prompts, fallback, audit) but stopped
short of wiring a real LLM. The only invokers shipped were
`ScriptedClaudeInvoker` (test fixtures) and `RefusingClaudeInvoker`
(safe default that always raises). The flag `--backend claude` was
operational but every call fell back to templated.

MKT-4B completes the loop by adding the first real
:class:`ClaudeInvoker`: :class:`AnthropicSDKInvoker`. It talks to
the Anthropic API via the official Python SDK. The user picked
this option over Claude Code subprocess (analysis: superior
traceability, cleaner credential boundary, lighter dependency,
better fit for backend automation).

The cardinal constraint, set by the user before approving:

- **No retries.** One attempt per method. If it fails, fall back.
- **`anthropic` is an OPTIONAL extra**, never a hard runtime dep.
- **Tests never hit the real API.** Two layers of defense.
- **Templated remains the default.** Zero behavior change without
  the flag.

## Decision

### D-16.1 — Anthropic SDK over subprocess

`AnthropicSDKInvoker` uses `anthropic.Anthropic(api_key=...).messages.create(...)`.
The subprocess route (`claude -p ...`) was rejected: it requires
Claude Code installed in production, parses stdout (fragile to
chrome / ANSI / version drift), loses token counts and request_ids,
and on Windows compounds the project's existing cp1252 encoding
issues.

### D-16.2 — Optional dependency under extra `claude`

```toml
[project.optional-dependencies]
claude = ["anthropic>=0.40,<1.0"]
```

The templated backend has zero LLM dependencies. Installing the
project (`pip install -e .`) does NOT install `anthropic`. To use
`--backend claude` the operator opts in with `pip install -e .[claude]`.
If the SDK is missing AND the operator passes `--backend claude`,
the invoker constructor raises `NoCredentialsError` (re-used as the
"no SDK" sentinel — same fallback path as "no API key"), the CLI
warns on stderr and falls back to templated. Exit 0.

### D-16.3 — Credential boundary

The key flow:

1. Read from `ANTHROPIC_API_KEY` env var (or explicit `api_key=`
   kwarg) **once**, at invoker construction.
2. Passed to the `Anthropic(api_key=...)` SDK client.
3. The invoker keeps NO long-lived reference to the raw key (the
   SDK client holds it).
4. `__repr__` returns `AnthropicSDKInvoker(api_key=***redacted***, model=..., timeout_s=...)`.
5. No error message constructed by our code includes the key. The
   raised `ClaudeInvokerError` wraps `type(exc).__name__: str(exc)[:160]`.
6. The Pydantic model `ClaudeInvocationRecord` has NO `api_key` /
   `key` / `secret` / `token` / `credential` field. Tests assert
   this invariant programmatically.

If the SDK itself echoes the key in an exception message, that's
upstream's problem; our boundary truncates the message to 160 chars
and routes it only to the local audit trail + summary on disk. The
key value is never logged to stdout, stderr, or any file the
operator did not opt into.

### D-16.4 — One attempt per method, mandatory fallback

The invoker does **not** retry. Every error class
(`AuthenticationError`, `RateLimitError`, `APITimeoutError`,
`APIConnectionError`, `APIError`, anything else) maps to a single
raised `ClaudeInvokerError`, which the `ClaudeStrategyBackend`
catches via the catch-all already in place since MKT-4A. The
backend then delegates to its `fallback` (default:
`TemplatedStrategyBackend`).

Retries are explicitly deferred to **P-4B.1**. Adding them now
would (a) complicate the cost model, (b) hide rate-limit signals
the operator needs to see, (c) couple this block to a policy
decision (exponential vs linear, jitter, budget) that has no
operational data behind it.

### D-16.5 — Invocation records via additive sink

A new optional field `record_sink: list | None = None` was added
to `ClaudeInvocationContext`. When set, real invokers append
exactly one `ClaudeInvocationRecord` per call (success OR failure).
The mock invokers ignore the field.

This was chosen over three alternatives:

| Alternative                                    | Reason for rejection |
|------------------------------------------------|----------------------|
| Change `complete()` to return `(text, record)` | Breaks MKT-4A signature; cascades to 12+ tests. |
| Add `pop_last_record()` to `ClaudeInvoker` ABC | Forces empty-impls on Scripted/Refusing.       |
| Thread-local storage / global registry         | Stateful; not safe under future concurrency.   |

The sink approach is purely additive and the record always lands
in `try/finally` so the orchestrator collects it even when the
invoker raises.

### D-16.6 — Three new audit event sub-actions

Under `payload.campaign_pipeline`:

- `action="strategy_backend_invocation"` — one per real LLM call
  attempt. Carries `method`, `model`, `request_id`, `input_tokens`,
  `output_tokens`, `duration_ms`, `ok`, `error_type`.
- `action="strategy_backend_fallback"` — unchanged from MKT-4A. One
  per fallback event.
- `action="succeeded"` (strategy stage) — now carries
  `fallback_count` (additive, MKT-4A).

The hash chain is preserved end-to-end. Tested in
`tests/pipeline/test_orchestrator_invocations.py`.

### D-16.7 — `CampaignRunSummary` gains `claude_invocations`

Additive field, default `[]`. Never None. Empty when the templated
backend ran. One record per attempt when the Claude backend ran
(success OR failure). The contract version (`pipeline-run.v1`)
stays unchanged because the addition is backward-compatible:
existing summaries parse cleanly, new summaries serialise into
`claude_invocations: []` for templated runs.

### D-16.8 — CLI behavior matrix

| `--backend` | `ANTHROPIC_API_KEY` | `anthropic` installed | Invoker wired             | Effective |
|-------------|---------------------|-----------------------|---------------------------|-----------|
| (default)   | any                 | any                   | none (templated only)     | templated |
| `templated` | any                 | any                   | none (templated only)     | templated |
| `claude`    | absent              | any                   | `RefusingClaudeInvoker`   | templated (warns) |
| `claude`    | present             | absent                | `RefusingClaudeInvoker` (after `NoCredentialsError`) | templated (warns) |
| `claude`    | present             | present, SDK errors   | `AnthropicSDKInvoker` (raises per-method)            | templated (fallback x6 with audit) |
| `claude`    | present             | present, valid JSON   | `AnthropicSDKInvoker`     | claude    |
| `claude`    | present             | present, mixed        | `AnthropicSDKInvoker`     | mixed     |

In every case CLI exit is 0 (subject to `--require-approval` and
`--stop-on-blocked` which are orthogonal). Warnings go to **stderr
only** so stdout JSON output is always parseable.

### D-16.9 — `--claude-model` flag and `ANTHROPIC_MODEL` env var

Resolution order: explicit `--claude-model` > `ANTHROPIC_MODEL` env
var > package default constant `DEFAULT_ANTHROPIC_MODEL` (currently
`claude-sonnet-4-5-20250929`). Tests cover all three levels and
verify the chosen model appears in every `ClaudeInvocationRecord.model`.

## Consequences

### Positive

- Real Claude generation available behind one flag; templated path
  is byte-identical to MKT-4A for any operator who does not opt in.
- Per-call traceability: model id, request id, tokens, duration, ok
  flag, sanitised error — all in the run summary and the audit trail.
- Cost ceiling visible: max 6 calls × `max_tokens=2048` per run.
- CI safety: pytest passes with no `anthropic` installed and no env
  var set. 869/869 green.
- Zero credential surface in the repo or in logs.

### Negative / accepted trade-offs

- No retry logic. A rate-limited operator sees 6 fallbacks, not a
  recovered run. Acceptable for v1 because fallbacks are observable
  (audit + summary + stderr) and the templated content is always
  valid.
- The optional extra means `--backend claude` can succeed in
  installation but fail at runtime if the operator forgot the
  extra. The CLI warning is explicit about this.
- The lazy import of `anthropic` masks import errors as
  `NoCredentialsError("anthropic package not installed")` — a
  small abstraction, but consistent with the "fall back cleanly"
  contract.
- SDK version drift is a real risk; pinned to `>=0.40,<1.0`. A new
  major release will fail tests first, not production.

## Out of scope (explicit)

- No MCP, no n8n, no GA4, no Google Ads, no Search Console.
- No image generation, no publishing, no email sending.
- No Claude Code subprocess invoker.
- No retries (P-4B.1).
- No streaming (P-4B.2).
- No prompt caching (P-4B.5).
- No multi-model cascade (P-4B.4).
- No cost dashboard or per-tenant budget (P-4B.3).
- No async invoker (P-4B.6).
- No Bedrock / Vertex / other providers.
- No real network call in tests, ever.

## Validation

- 23 new tests (invokers/test_anthropic_sdk.py + test_invocation_log.py
  + test_cli_backend_claude_sdk.py + test_orchestrator_invocations.py).
- Full suite: **869 passed**.
- Ruff: **clean**.
- ATLAS core: untouched.
- Smoke verified: `--backend claude` with no env var → exit 0, six
  fallbacks, audit chain valid, summary on disk.

## Related

- Depends on MKT-4A (`StrategyBackend` ABC, `ClaudeStrategyBackend`,
  `ClaudeInvoker` ABC, `record_sink` channel).
- Future work tracked under `P-4B.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/anthropic-sdk-invoker.md`.
