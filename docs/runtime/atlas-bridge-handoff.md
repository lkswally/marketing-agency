# ATLAS Bridge Handoff (MKT-8A)

Runtime guide for `mkt atlas-brief`. Emits a structured handoff
brief (Markdown + JSON) the operator copies into the ATLAS
workflow manually. **No HTTP. No reach-in into ATLAS.**

## Quick start

```bash
# Pre-req: a CampaignStrategyReport for the client (run-strategy
# or run-campaign). Approval / creative / visual / image-job
# packs are read best-effort when present.
mkt run-campaign --intake examples/intake/demo-business.json
mkt image-jobs   --client <slug>

mkt atlas-brief --client <slug> --kind landing
mkt atlas-brief --client <slug> --kind branding
mkt atlas-brief --client <slug> --kind page_design --page-name pricing
```

Outputs land in `outputs/<slug>/`:

| Kind          | Filename                                |
|---------------|------------------------------------------|
| `landing`     | `atlas-landing-brief.{md,json}`         |
| `branding`    | `atlas-branding-brief.{md,json}`        |
| `page_design` | `atlas-page-design-brief.{md,json}`     |

The pack is also persisted under
`<root>/<client>/atlas_handoff_brief/current.json`.

Concrete examples (real CLI output, not hand-written) live in
[`examples/atlas-bridge/`](../../examples/atlas-bridge/).

## Contract structure

`AtlasHandoffBrief` (envelope) wraps exactly one of:

- `LandingBrief`     — `landing-brief.v1`
- `BrandingBrief`    — `branding-brief.v1`
- `PageDesignBrief`  — `page-design-brief.v1`

Each carries: objective + target audience + approved copy +
visual style notes + asset references (text-only) + SEO/GEO
targets + constraints + acceptance criteria.

For the full spec (every field, every cardinal rule, evolution
policy), read
[`docs/decisions/0031-mkt-8a-alpha-pilot-atlas-bridge.md`](../decisions/0031-mkt-8a-alpha-pilot-atlas-bridge.md).

## What the brief does NOT carry

- No credential, token, api_key, webhook URL.
- No binary asset (no inline PNG/JPG).
- No deadline / pricing / revenue data.
- No URL the operator must POST to.

## Behaviour matrix

| State                                          | Result                                                    |
|------------------------------------------------|-----------------------------------------------------------|
| Strategy report exists                          | Exit 0; brief built; warning if upstream `blocks_publish`.|
| Approval pack `blocks_publish=True`             | `AtlasHandoffBrief.blocks_publish=True`; warning banner.  |
| Visual pack `blocks_publish=True`               | Same.                                                     |
| No strategy report                              | Exit 2.                                                   |
| Unsupported `--kind`                            | Exit 2 (argparse).                                        |

## Audit trail

Wrapped in `note` payload:

```json
{
  "atlas_handoff_brief": {
    "action": "built",
    "handoff_id": "...",
    "kind": "landing",
    "strategy_report_id": "...",
    "blocks_publish": false,
    "rule_set_id": "atlas-bridge.v1"
  }
}
```

Native `atlas_handoff_brief.v1` envelope tracked as P-8A.7.

## Cardinal guarantees (test-pinned)

| Guarantee                                                                  | Test                                               |
|----------------------------------------------------------------------------|----------------------------------------------------|
| No HTTP library in `core/atlas_bridge/`                                    | `test_no_http_lib_in_atlas_bridge_module`          |
| No ATLAS reach-in (`atlas_core`, `from atlas`, `ATLAS_API_URL`, …)         | `test_no_atlas_reach_in_anywhere`                  |
| No credential / env-var read                                               | `test_no_credential_read_in_source`                |
| No credential field on any model                                            | `test_no_credential_fields_on_any_model`           |
| Envelope rejects 0 / >1 briefs and kind mismatch                            | `test_handoff_rejects_zero_briefs`, `…_multiple_briefs`, `…_kind_mismatch` |
| Read-only over upstream packs                                              | `test_factory_does_not_mutate_upstream_packs`      |
| `LandingSection.body_copy` does not shadow `BaseModel.copy`                | `test_landing_section_body_copy_does_not_shadow_copy_method` |

## Exit codes

- `0` on success.
- `2` when no strategy report exists for the client OR
  `--kind` is invalid.

## Related docs

- [Alpha Pilot Playbook](../alpha-pilot-playbook.md)
- [Alpha Pilot Checklist](../alpha-pilot-checklist.md)
- [Alpha Pilot Definition of Ready](../alpha-pilot-definition-of-ready.md)
- [Alpha Pilot Definition of Done](../alpha-pilot-definition-of-done.md)
- [Real-Business Intake Template](../real-business-intake-template.md)
- [ADR 0031 — Alpha Pilot + ATLAS Bridge](../decisions/0031-mkt-8a-alpha-pilot-atlas-bridge.md)
