# Agents — Index

> Status: **specs only** (MKT-1E). 16 agents defined; none implemented.
> Spec format: `agent-spec.v1` (frontmatter YAML + markdown body).

## What is an agent?

An agent is a **role spec** in `agents/<agent_id>.md` describing what the
role does in an agency: inputs, outputs, phase gates consumed/produced,
skills used, risks and limits. The runtime that executes them (Claude Code
subagent spawn, future Python wrapper) does not exist yet — see ADR 0005.

## The 16 agents

| Agent | Role | Phase(s) | Default model | Skills |
|-------|------|----------|---------------|--------|
| [mkt-orchestrator](../agents/mkt-orchestrator.md) | orchestrator | intake, assemble | opus | — |
| [brand-strategist](../agents/brand-strategist.md) | strategist | strategy, offer | opus | brand-voice-extractor, icp-definition |
| [audience-researcher](../agents/audience-researcher.md) | researcher | research | sonnet | icp-definition |
| [keyword-intelligence-agent](../agents/keyword-intelligence-agent.md) | researcher | keywords | sonnet | keyword-research, negative-keywords, hashtag-research |
| [competitor-benchmark-agent](../agents/competitor-benchmark-agent.md) | researcher | competitor | sonnet | competitor-benchmark |
| [channel-advisor-agent](../agents/channel-advisor-agent.md) | strategist | channel_mix | sonnet | channel-recommendation |
| [paid-ads-strategist](../agents/paid-ads-strategist.md) | strategist | channel_mix | sonnet | paid-ads-plan |
| [seo-content-planner](../agents/seo-content-planner.md) | strategist | channel_mix | sonnet | seo-content-plan |
| [copywriter](../agents/copywriter.md) | producer | copy, social, email | sonnet | landing-copy, email-sequence-draft, social-post-draft |
| [creative-director](../agents/creative-director.md) | producer | brief, bundle | opus | creative-brief |
| [reels-scriptwriter](../agents/reels-scriptwriter.md) | producer | social | sonnet | reels-script |
| [compliance-auditor](../agents/compliance-auditor.md) | validator | compliance | opus | claim-validator |
| [approval-manager](../agents/approval-manager.md) | coordinator | package, approval | sonnet | approval-packager |
| [analytics-agent](../agents/analytics-agent.md) | analyst | analyze, report | sonnet | — |
| [optimizer-agent](../agents/optimizer-agent.md) | strategist | optimize | sonnet | optimization-recommendation |
| [n8n-automation-planner](../agents/n8n-automation-planner.md) | planner | — (out-of-workflow) | sonnet | — |

## Model routing

| Model | Used by | Rationale |
|-------|---------|-----------|
| opus | mkt-orchestrator, brand-strategist, creative-director, compliance-auditor | Strategy, creative direction, compliance verdicts — high-stakes reasoning. |
| sonnet | All others (11 agents) | Execution of structured tasks. |

The runtime resolves the model per spawn (future MKT-2A). Specs declare the
default; orchestrator policy may override.

## Status

Every agent has `status: spec_only` in its frontmatter. The future
dispatcher MUST refuse to spawn an agent whose status is not `implemented`.
Promotion to `implemented` happens block by block.

## Gates this index implies

Aggregated gates the agent set produces (full grammar in
[workflows/overview.md](workflows/overview.md)):

`g_brief_captured`, `g_audience_research_complete`, `g_competitor_baseline`,
`g_keywords_drafted`, `g_positioning_drafted`, `g_brand_voice_captured`,
`g_channels_proposed`, `g_offer_drafted`, `g_campaign_drafted`,
`g_creative_brief_ready`, `g_copy_drafted`, `g_social_drafted`,
`g_email_drafted`, `g_creatives_drafted`, `g_compliance_passed`,
`g_approval_packaged`, `g_approval_granted`, `g_metrics_summarized`,
`g_optimization_recommended`, `g_report_drafted`, `g_n8n_plan_drafted`.

## How to add a new agent

1. Add `agents/<agent_id>.md` with the `agent-spec.v1` frontmatter.
2. Update this index.
3. Add `agent_id` to the workflow(s) that use it.
4. If the agent uses a new skill, add the skill spec under `skills/`.
5. Add the produced gate to `docs/workflows/overview.md` §3.
