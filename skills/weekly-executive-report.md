---
skill_id: weekly-executive-report
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - client_slug: str
  - market_intelligence_pack: MarketIntelligencePack
  - analytics_snapshot: AnalyticsSnapshot  # optional
  - ads_feedback_pack: AdsFeedbackPack     # optional
  - iteration_plan: IterationPlan          # optional
outputs:
  - report_md: str
  - report_json: dict
used_by: [executive-reporter-agent]
---

# weekly-executive-report

## What
Produces a concise weekly executive report (Markdown + JSON) that summarises:
1. Market signals (top trend + competitor activity).
2. Performance highlights (best channel, key metric changes).
3. Creative health (fatigued pieces, recommended rotations).
4. Budget pacing status.
5. Top 3 recommended actions for the week.

## When
- Once per week, after market intelligence pack is updated.
- On demand when the client requests a status summary.

## Heuristics
- Max length: 800 words in Markdown.
- Lead with the single most important insight (rising trend or competitor threat).
- Actions must be concrete and actionable (verb-first, owner implied).
- If no analytics data: skip performance section with explicit note.

## Failure modes
- No market intelligence pack → abort with error; this skill requires it.
- Partial data (analytics missing) → generate partial report; note missing sections.

## Out of scope
- Deep channel-level attribution analysis (future analytics skill).
- Automated distribution of the report (Notion/Slack/email — separate integrations).
