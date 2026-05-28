---
skill_id: claim-validator
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - claims: list[Claim]
  - evidence: list[Evidence]
outputs:
  - updated_claims: list[Claim]
  - claim_audit: ClaimAudit
used_by: [compliance-auditor]
---

# claim-validator

## What
Assigns `severity` and `verdict` to each Claim and produces a `ClaimAudit`
block. Compares each Claim's `evidence_ids` to the supplied Evidence list.

## When
- W5.compliance, per Asset with claims.

## Heuristics
- A claim with no Evidence ref → verdict `unverified`.
- A claim whose evidence contradicts the text → verdict `contradicted`.
- A claim verified by ≥1 Evidence with `trust_level ≥ 0.7` → `verified`.
- Comparative claims ("3x faster") require either a benchmark Evidence or
  the rationale notes the comparison basis.

## Failure modes
- Missing Evidence list → run with claim text alone; verdicts default to
  `unverified`.
- Severity assignment is conservative: when in doubt, escalate.

## Out of scope
- Re-running the claim through a fact-checking API (no API in v1).
- Translating claims across languages.
