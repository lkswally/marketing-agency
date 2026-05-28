---
skill_id: approval-packager
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - assets: list[Asset]
  - claim_audits: list[ClaimAudit]
outputs:
  - approval: Approval     # memory entity (kind="approval")
used_by: [approval-manager]
---

# approval-packager

## What
Bundles the post-compliance creative set into a single Approval entity.
Snapshots each artifact's SHA-256 so the decision references a frozen
version.

## When
- W5.package.

## Heuristics
- One Approval per Campaign per W5 run (not one per Asset).
- `artifact_refs` lists every Asset with its current sha256 + kind +
  entity_id.
- `related_claim_audit` is a snapshot, not a reference.

## Failure modes
- Asset hash cannot be computed (binary missing) → flag the artifact in
  `incomplete_refs`, do not block packaging.

## Out of scope
- Notification (Slack, email).
- UI rendering of the package.
