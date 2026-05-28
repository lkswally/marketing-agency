# Skills — Index

> Status: **specs only** (MKT-1E). 17 skills defined; none implemented.
> Spec format: `skill-spec.v1` (frontmatter YAML + markdown body).

## What is a skill?

A skill is an **atomic capability** that agents compose. Skills do not call
other skills (no recursion); agents orchestrate them.

A skill spec declares its inputs, outputs, whether it is `deterministic`,
its `external_dependencies`, and which agents `use` it.

## The 17 skills

| Skill | Used by | Deterministic | External deps |
|-------|---------|---------------|---------------|
| [brand-voice-extractor](../skills/brand-voice-extractor.md) | brand-strategist, copywriter | no | — |
| [icp-definition](../skills/icp-definition.md) | audience-researcher, brand-strategist | no | — |
| [keyword-research](../skills/keyword-research.md) | keyword-intelligence-agent | no | — |
| [negative-keywords](../skills/negative-keywords.md) | keyword-intelligence-agent | no | — |
| [hashtag-research](../skills/hashtag-research.md) | keyword-intelligence-agent | no | — |
| [competitor-benchmark](../skills/competitor-benchmark.md) | competitor-benchmark-agent | no | — |
| [channel-recommendation](../skills/channel-recommendation.md) | channel-advisor-agent | no | — |
| [paid-ads-plan](../skills/paid-ads-plan.md) | paid-ads-strategist | no | — |
| [seo-content-plan](../skills/seo-content-plan.md) | seo-content-planner | no | — |
| [landing-copy](../skills/landing-copy.md) | copywriter | no | — |
| [email-sequence-draft](../skills/email-sequence-draft.md) | copywriter | no | — |
| [social-post-draft](../skills/social-post-draft.md) | copywriter | no | — |
| [creative-brief](../skills/creative-brief.md) | creative-director | no | — |
| [reels-script](../skills/reels-script.md) | reels-scriptwriter | no | — |
| [claim-validator](../skills/claim-validator.md) | compliance-auditor | no | — |
| [approval-packager](../skills/approval-packager.md) | approval-manager | partial | — |
| [optimization-recommendation](../skills/optimization-recommendation.md) | optimizer-agent | no | — |

No skill in v1 has external dependencies (no API keys, no live data, no
external SDKs). Skills with `external_dependencies: []` are safe to spec
ahead of any integration work.

## Why no recursion

A skill does not invoke another skill directly. If a workflow needs the
composition of two capabilities, an agent owns the composition. This keeps
skill specs short, testable in isolation, and replaceable.

## Promotion path

`spec_only` → `implemented` (per skill) as later blocks land. Promotion
requires:

1. A concrete prompt or function (depending on whether the skill is
   reasoning-driven or deterministic).
2. Tests in `tests/skills/<skill_id>/` (out of scope for MKT-1E).
3. A status update in the skill's frontmatter.

## How to add a new skill

1. Add `skills/<skill_id>.md` with the `skill-spec.v1` frontmatter.
2. Update this index.
3. Reference the skill in the agent(s) that will use it (`skills:` field).
