---
skill_id: budget-pacer
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: true
external_dependencies: []
inputs:
  - total_budget: float
  - spent_to_date: float
  - days_elapsed: int
  - days_total: int
  - channel_allocations: dict[str, float]  # channel → budget fraction
outputs:
  - pacing_status: str  # "on_track" | "underspending" | "overspending"
  - daily_run_rate: float
  - recommended_daily_budget: float
  - channel_adjustments: dict[str, float]  # channel → adjustment factor
  - notes: list[str]
used_by: [ads-optimization-agent]
---

# budget-pacer

## What
Computes whether campaign spend is pacing correctly and recommends daily
budget adjustments per channel to hit the total budget exactly by end of
period.

## When
- During ads feedback cycle (daily or weekly).
- When the client asks "are we on pace to spend our budget this month?".

## Heuristics
- Ideal daily rate = total_budget / days_total.
- Actual rate = spent_to_date / max(days_elapsed, 1).
- Overspending threshold: actual_rate > ideal_rate * 1.15.
- Underspending threshold: actual_rate < ideal_rate * 0.85.
- Channel adjustment = ideal_remaining_by_channel / remaining_days.

## Failure modes
- days_elapsed = 0 → return `on_track` with recommended rate = ideal_rate.
- spent_to_date > total_budget → return `overspending` immediately, no further computation.

## Out of scope
- Automated budget mutation in the ads platform (read-only; operator applies adjustments).
- Multi-currency normalization (assume single currency).
