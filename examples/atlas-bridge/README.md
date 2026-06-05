# `examples/atlas-bridge/` — sample handoffs (MKT-8A)

The Markdown + JSON files in this directory are real CLI outputs
captured from `mkt atlas-brief`, **not** hand-written examples.

## How they were produced

```bash
mkt run-campaign --intake examples/intake/demo-business.json \
  --root /tmp/mkt8a-sample/mem \
  --outputs-dir /tmp/mkt8a-sample/out

mkt image-jobs --client acme-bootstrapped \
  --root /tmp/mkt8a-sample/mem \
  --outputs-dir /tmp/mkt8a-sample/out/acme-bootstrapped

mkt atlas-brief --client acme-bootstrapped --kind landing \
  --root /tmp/mkt8a-sample/mem \
  --outputs-dir /tmp/mkt8a-sample/out/acme-bootstrapped

mkt atlas-brief --client acme-bootstrapped --kind branding \
  --root /tmp/mkt8a-sample/mem \
  --outputs-dir /tmp/mkt8a-sample/out/acme-bootstrapped

mkt atlas-brief --client acme-bootstrapped --kind page_design \
  --root /tmp/mkt8a-sample/mem \
  --outputs-dir /tmp/mkt8a-sample/out/acme-bootstrapped
```

Then the three pairs were copied verbatim to this directory and
renamed:

| Source                                                  | Example name                          |
|----------------------------------------------------------|----------------------------------------|
| `outputs/.../atlas-landing-brief.{md,json}`              | `landing-handoff-example.{md,json}`    |
| `outputs/.../atlas-branding-brief.{md,json}`             | `branding-handoff-example.{md,json}`   |
| `outputs/.../atlas-page-design-brief.{md,json}`          | `page-design-handoff-example.{md,json}` |

## Why this matters

- Operators and ATLAS engineers reading the examples see exactly
  what the CLI emits — no hand-massaged content that the factory
  might not actually produce.
- When the contract evolves, regenerating these examples is one
  pipeline run away.
- No credential, URL, or binary asset appears anywhere — pinned
  by the MKT-8A test suite.

## Regenerating

Replay the commands above on any machine. The `handoff_id` and
timestamps will differ; the shape will not.
