# Runtime — Anthropic SDK Invoker (MKT-4B)

The Anthropic SDK invoker is the first real :class:`ClaudeInvoker`
implementation. It lets `mkt run-campaign --backend claude` produce
LLM-backed strategy content (value proposition, campaign strategy,
creative brief pack, social posts, email sequence, reels scripts),
with deterministic fallback to the templated backend on any error.

- **Module:** `core/strategy/backends/invokers/anthropic_sdk.py`
- **Class:** `AnthropicSDKInvoker(ClaudeInvoker)`
- **Optional dep:** `anthropic>=0.40,<1.0` (extra `claude`)
- **Default model:** `claude-sonnet-4-5-20250929`

## Quick start

```bash
pip install -e .[claude]
export ANTHROPIC_API_KEY="sk-ant-..."           # required
export ANTHROPIC_MODEL="claude-sonnet-4-5-20250929"  # optional override

mkt run-campaign --intake examples/intake/demo-business.json --backend claude
```

Without `--backend claude`, the SDK is never imported. Without
`ANTHROPIC_API_KEY`, the CLI warns on stderr and falls back to
the templated backend (`backend_effective=templated`, exit 0).

## Where the API key lives

The key is read **once** from the `ANTHROPIC_API_KEY` env var (or
passed explicitly to the invoker constructor). After that:

- It is passed to the `anthropic.Anthropic(...)` SDK client at
  construction time, then the invoker drops its own reference.
- It is **never** written to disk, the audit trail, the Pydantic
  invocation record, or any error message produced by this code.
- `repr(invoker)` redacts it to `***redacted***`.

You are responsible for the credential lifecycle outside the
process:

- Local dev: `.env` (gitignored) loaded by your shell or a tool like
  `direnv` / `dotenv`. The repo's `.gitignore` already excludes `.env`.
- CI: never set `ANTHROPIC_API_KEY` in CI by default. Use a separate
  job for integration testing if and when needed (see "Testing without
  burning tokens" below).
- Production: a secret manager (Vercel env vars, GCP Secret Manager,
  AWS Secrets Manager, Doppler, 1Password Connect). Inject as env
  var at process start.

## How the invoker behaves

For each of the six creative methods, the
:class:`ClaudeStrategyBackend`:

1. Builds a prompt with `core/strategy/backends/prompts.py`.
2. Creates an empty list (`record_sink`) and a
   :class:`ClaudeInvocationContext`.
3. Calls `invoker.complete(prompt, system=..., context=...)`.
4. Parses the response as JSON (strips optional markdown fences).
5. Validates with Pydantic.
6. On any error (auth, rate limit, timeout, connection, generic API
   error, oversized output, JSON parse error, Pydantic validation
   error) → records a fallback event and delegates to the templated
   backend.

The invoker always appends exactly one
:class:`ClaudeInvocationRecord` to `record_sink`:

- On success: `ok=True`, with `model`, `request_id`, `input_tokens`,
  `output_tokens`, `duration_ms`.
- On failure: `ok=False`, with `error_type` (the SDK exception class
  name) and a sanitised `error_message` (≤ 160 chars).

The records flow up to `CampaignRunSummary.claude_invocations` and
are mirrored as `audit-trail.v1` events with payload
`{"campaign_pipeline": {"action": "strategy_backend_invocation", ...}}`.
The hash chain is preserved.

## Error mapping

| SDK error             | What happens                                    |
|-----------------------|-------------------------------------------------|
| `AuthenticationError` | Fallback. `error_type="AuthenticationError"`.   |
| `RateLimitError`      | Fallback. `error_type="RateLimitError"`.        |
| `APITimeoutError`     | Fallback. `error_type="APITimeoutError"`.       |
| `APIConnectionError`  | Fallback. `error_type="APIConnectionError"`.    |
| Other `APIError`      | Fallback. `error_type="APIError"`.              |
| Anything else         | Fallback. `error_type=<class name>`.            |

Every error path: appends a record with `ok=False`, raises
`ClaudeInvokerError`, the backend catches and falls back. The
pipeline exits 0 in every case (subject to the regular
`--require-approval` / `--stop-on-blocked` semantics).

No retries are performed in MKT-4B. One attempt per method. If you
need retries, see `PENDING.md` → P-4B.1.

## Cost ceiling

Per `mkt run-campaign --backend claude` with Sonnet 4.5 (defaults):

- 6 calls × ~3K input tokens × $3/M = **~$0.054**
- 6 calls × ~1K output tokens × $15/M = **~$0.090**
- **Worst-case total ≈ $0.15/run** with the 2048 max_tokens cap.

In practice prompts are smaller (the templates are short and the
input brief is one JSON object). Typical: **~$0.02–0.04/run**.

To use a cheaper model:

```bash
export ANTHROPIC_MODEL="claude-haiku-4-5-20251001"
# or
mkt run-campaign --intake ... --backend claude --claude-model claude-haiku-4-5-20251001
```

## Testing without burning tokens

Two layers of defense ensure tests never hit the real API:

1. **Dependency injection.** The constructor accepts a `client=`
   kwarg. Tests pass a `MagicMock`. The real
   `anthropic.Anthropic(...)` call is gated on `client is None`.
2. **Lazy import.** `import anthropic` only runs inside the
   constructor when `client is None`. Mocking suppresses the import
   path completely.

CI runs the full pytest suite (`pytest`) without `ANTHROPIC_API_KEY`
and without the `anthropic` package installed. All 869 tests pass.

If you want an integration test against the real API, mark it
`@pytest.mark.integration` and run with the marker enabled — the
repo's `pyproject.toml` declares the marker but `addopts` does NOT
include integration tests by default.

## Anti-patterns

- **Do not** `print(os.environ["ANTHROPIC_API_KEY"])` in any code
  path (logging, debugging, error messages).
- **Do not** commit `.env`, `secrets.json`, or any file with a real
  key. The `.gitignore` already covers `.env` and `.env.*`.
- **Do not** add `anthropic` to `[project.dependencies]` (runtime
  deps). It is an optional extra under `[project.optional-dependencies].claude`
  on purpose — the templated backend works without it.
- **Do not** retry inside the invoker. Fallback is the contract.
  Retries belong outside (a future block adds them with explicit
  budgets).
- **Do not** widen the timeout beyond 30 s without re-evaluating
  the deadlock risk (the pipeline is single-threaded).

## What's NOT in MKT-4B

- No retries (P-4B.1).
- No streaming (P-4B.2).
- No prompt caching / `cache_control` (P-4B.5).
- No multi-model fallback / cascade (P-4B.4).
- No cost-tracking dashboard or per-tenant budget (P-4B.3).
- No async invoker (P-4B.6).
- No Bedrock, no Vertex AI, no other providers. Only Anthropic API.

## Sample output

`campaign-final-summary.md` now includes a "Strategy backend"
section with a per-call table:

```markdown
## 01b. Strategy backend

- **Backend solicitado**: 🤖 `claude`.
- **Backend efectivo**: 🤖 `claude` (sin fallback).

**Invocaciones a Claude (6)**:
| Método | Modelo | Request ID | In | Out | Duración (ms) | OK |
|--------|--------|------------|----|----|---------------|-----|
| `value_proposition` | `claude-sonnet-4-5-20250929` | `req_01H...` | 423 | 187 | 1820.4 | ✅ |
| `campaign_strategy` | `claude-sonnet-4-5-20250929` | `req_01H...` | 612 | 244 | 2104.7 | ✅ |
| ...
```

If a fallback happened, the table shows `OK=❌` for that row and the
fallback notes block lists the method + reason.
