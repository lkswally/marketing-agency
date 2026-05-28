---
skill_id: social-post-draft
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - brand: Brand
  - audience: Audience
  - channel: Channel
  - creative_brief: Asset
outputs:
  - assets: list[Asset]
  - claims: list[Claim]
used_by: [copywriter]
---

# social-post-draft

## What
Drafts a small batch of posts for a single social channel. The shape of the
post adapts to channel: LinkedIn paragraph, X thread, IG caption, etc.

## When
- W4.social.

## Heuristics
- 3–7 posts per channel per run.
- Each post has a hook, body, and one CTA.
- Hashtags only on channels that use them.

## Failure modes
- Unknown channel type → return empty list with a note.

## Out of scope
- Scheduling.
- Image generation.
