---
skill_id: creative-fatigue-scorer
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: true
external_dependencies: []
inputs:
  - pieces: list[SuggestedPiece]
  - performance_metrics: AnalyticsSnapshot  # optional
outputs:
  - fatigue_scores: dict[str, float]  # piece_id → score 0–100
  - fatigued_pieces: list[str]        # piece_ids with score >= threshold
used_by: [iteration-planner-agent]
---

# creative-fatigue-scorer

## What
Scores each creative piece for fatigue risk based on run age, impression
volume, and CTR decay. A score of 100 means definitely fatigued; 0 means
fresh.

## When
- During the iteration planning cycle (before IterationPlan generation).
- When an A/B test has been running > 14 days with declining CTR.

## Heuristics
- Fatigue threshold: score >= 70.
- Score components:
  - Age component: min(piece_age_days / 30 * 50, 50).
  - CTR decay component: if current_ctr < 50% of launch_ctr → +30; else +0.
  - Impression volume component: if impressions >= 50 000 → +20; else +0.
- If no performance metrics → score = age component only.

## Failure modes
- Missing piece metadata → score = 0 (assume fresh), surface a warning.
- No analytics data → partial scoring using age only; note this in output.

## Out of scope
- Video completion rate fatigue (requires video analytics, future).
- Copy-level fatigue (vs. visual fatigue) — not distinguished in this version.
