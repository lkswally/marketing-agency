"""GoogleAdsAnalyzer — deterministic per-ad-group rule engine.

Reads ``MetricsSnapshot`` rows tagged with ``MetricSource.GOOGLE_ADS``,
aggregates them per ``content_ref`` (campaign + ad_group), and
applies a fixed set of rules to surface actionable insights.

**No mutation** of Google Ads state. **No external API.** The pack
contains suggestions; the operator decides what (if anything) to
change in the Ads UI.

Rules implemented (severity in parentheses):

1. **High spend, zero conversions** (HIGH) — cost ≥
   ``_HIGH_SPEND_ZERO_CONV_COST``, conversions == 0.
   Suggested action: ``pause_candidate``.
2. **High spend, low conversions** (HIGH) — cost ≥
   ``_HIGH_SPEND_LOW_CONV_COST``, 0 < conversions <
   ``_HIGH_SPEND_LOW_CONV_THRESHOLD``.
   Suggested action: ``review_campaign``.
3. **Low CTR, high impressions** (MEDIUM) — impressions ≥
   ``_LOW_CTR_MIN_IMPR``, ctr < ``_LOW_CTR_THRESHOLD``.
   Suggested action: ``improve_ad_copy``.
4. **Good CTR, low conversion rate** (MEDIUM) — ctr ≥
   ``_GOOD_CTR_THRESHOLD``, clicks ≥ ``_GOOD_CTR_MIN_CLICKS``,
   conversion_rate < ``_LOW_CONV_RATE_THRESHOLD``.
   Suggested action: ``review_landing``.
5. **High CPA outlier** (MEDIUM) — cpa > ``_HIGH_CPA_MULTIPLIER`` ×
   median cpa across the snapshot, conversions ≥ 1.
   Suggested action: ``review_ad_group``.
6. **Scale candidate** (MEDIUM) — conversions ≥
   ``_SCALE_MIN_CONVERSIONS``, cpa ≤ median cpa ×
   ``_SCALE_CPA_RATIO``, cost ≤ median cost.
   Suggested action: ``scale_candidate``.
7. **Budget review** (LOW) — campaign-level: campaign total cost
   in the top quartile of all campaigns in the snapshot.
   Suggested action: ``budget_review``.

All thresholds are module constants. Per-tenant overrides are
tracked as **P-6F.1**.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from statistics import median

from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)
from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory

from .models import (
    GOOGLE_ADS_INSIGHT_PACK_KIND,
    AdGroupProfile,
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)
from .models import SINGLETON_ID as PACK_SINGLETON

DEFAULT_ADS_ANALYZER_RULE_SET_ID = "ads-analyzer.v1"

# Rule thresholds — module-level constants. P-6F.1 tracks per-tenant
# overrides via a config file.
_HIGH_SPEND_ZERO_CONV_COST = 50.0
_HIGH_SPEND_LOW_CONV_COST = 100.0
_HIGH_SPEND_LOW_CONV_THRESHOLD = 2.0

_LOW_CTR_MIN_IMPR = 1000.0
_LOW_CTR_THRESHOLD = 0.02

_GOOD_CTR_THRESHOLD = 0.05
_GOOD_CTR_MIN_CLICKS = 100.0
_LOW_CONV_RATE_THRESHOLD = 0.01

_HIGH_CPA_MULTIPLIER = 2.0

_SCALE_MIN_CONVERSIONS = 3.0
_SCALE_CPA_RATIO = 0.7

_BUDGET_TOP_QUARTILE = 0.75


class GoogleAdsAnalyzer:
    """Deterministic rule engine over Google Ads metric rows."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # ---------- public API ----------

    def analyze(
        self, client_slug: str, *, rule_set_id: str | None = None,
    ) -> GoogleAdsInsightPack:
        snapshot = self._load_snapshot(client_slug)
        ads_rows = snapshot.rows_by_source(MetricSource.GOOGLE_ADS)
        profiles = _aggregate_profiles(ads_rows)
        insights = _apply_rules(profiles)
        stats = _build_stats(
            profiles=profiles, insights=insights, rows=len(ads_rows),
        )
        return GoogleAdsInsightPack(
            client_slug=client_slug,
            snapshot_id=snapshot.snapshot_id,
            snapshot_contract_version=snapshot.contract_version,
            profiles=profiles,
            insights=insights,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=rule_set_id or DEFAULT_ADS_ANALYZER_RULE_SET_ID,
        )

    def persist(self, pack: GoogleAdsInsightPack) -> None:
        self._memory.put(
            pack.client_slug,
            GOOGLE_ADS_INSIGHT_PACK_KIND,
            PACK_SINGLETON,
            pack.model_dump(mode="json"),
        )
        self._memory.append_audit_event_atomic(
            pack.client_slug,
            lambda prev_hash_arg: AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor="google_ads_analyzer",
                occurred_at=utcnow(),
                client_slug=pack.client_slug,
                payload={
                    "google_ads_insight_pack": {
                        "action": "analyzed",
                        "pack_id": pack.pack_id,
                        "snapshot_id": pack.snapshot_id,
                        "ad_groups_profiled": pack.stats.ad_groups_profiled,
                        "total_insights": pack.stats.total_insights,
                        "rule_set_id": pack.rule_set_id,
                    }
                },
                prev_hash=prev_hash_arg,
            ),
        )

    # ---------- internals ----------

    def _load_snapshot(self, client_slug: str) -> MetricsSnapshot:
        try:
            raw = self._memory.get(client_slug, METRICS_SNAPSHOT_KIND, SINGLETON_ID)
        except EntityNotFound as e:
            raise ValueError(
                f"no MetricsSnapshot for client {client_slug!r} — "
                "run `mkt analytics-fetch --source google_ads` or "
                "`mkt import-metrics` first"
            ) from e
        return MetricsSnapshot.model_validate(raw)


def analyze_and_persist_ads(
    memory: Memory, *, client_slug: str,
    rule_set_id: str | None = None,
) -> GoogleAdsInsightPack:
    """Run the analyzer + persist + audit in one call."""

    analyzer = GoogleAdsAnalyzer(memory=memory)
    pack = analyzer.analyze(client_slug, rule_set_id=rule_set_id)
    analyzer.persist(pack)
    return pack


# ---------- aggregation ----------


def _aggregate_profiles(rows: list[MetricRow]) -> list[AdGroupProfile]:
    """Group metric rows by ``content_ref`` and build one profile
    per ad-group. Rows whose ``content_ref`` is ``None`` are folded
    into a synthetic ``"__unattributed__"`` bucket — usually empty
    in practice because the MKT-6E normaliser always sets it."""

    buckets: dict[str, dict] = {}
    for r in rows:
        key = r.content_ref or "__unattributed__"
        b = buckets.setdefault(key, {
            "content_ref": key,
            "campaign_id": _parse_campaign_id(key),
            "ad_group_id": _parse_ad_group_id(key),
            "dimension": r.dimension,
            "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
            "conversions": 0.0, "conversions_value": 0.0,
            "sample_rows": 0,
        })
        # Prefer the latest non-empty dimension we see.
        if r.dimension and not b["dimension"]:
            b["dimension"] = r.dimension
        b["sample_rows"] += 1
        name = r.metric_name
        if name in ("impressions", "clicks", "cost", "conversions",
                    "conversions_value"):
            b[name] += float(r.value)

    profiles: list[AdGroupProfile] = []
    for b in buckets.values():
        impressions = b["impressions"]
        clicks = b["clicks"]
        cost = b["cost"]
        conversions = b["conversions"]
        ctr = (clicks / impressions) if impressions > 0 else None
        cpc = (cost / clicks) if clicks > 0 else None
        cpa = (cost / conversions) if conversions > 0 else None
        cvr = (conversions / clicks) if clicks > 0 else None
        profiles.append(AdGroupProfile(
            content_ref=b["content_ref"],
            campaign_id=b["campaign_id"],
            ad_group_id=b["ad_group_id"],
            dimension=b["dimension"],
            impressions=impressions,
            clicks=clicks,
            cost=cost,
            conversions=conversions,
            conversions_value=b["conversions_value"],
            ctr=ctr,
            cpc=cpc,
            cpa=cpa,
            conversion_rate=cvr,
            sample_rows=b["sample_rows"],
        ))
    # Deterministic order: highest cost first, then by content_ref.
    profiles.sort(key=lambda p: (-p.cost, p.content_ref))
    return profiles


def _parse_campaign_id(content_ref: str) -> str | None:
    # Shape: ``campaign:<id>::ad_group:<id>``.
    if not content_ref.startswith("campaign:"):
        return None
    head = content_ref.split("::", 1)[0]
    return head[len("campaign:"):] or None


def _parse_ad_group_id(content_ref: str) -> str | None:
    if "::ad_group:" not in content_ref:
        return None
    tail = content_ref.split("::ad_group:", 1)[1]
    return tail or None


# ---------- rules ----------


def _apply_rules(profiles: list[AdGroupProfile]) -> list[GoogleAdsInsight]:
    if not profiles:
        return []

    insights: list[GoogleAdsInsight] = []
    cpas = [p.cpa for p in profiles if p.cpa is not None]
    median_cpa = median(cpas) if cpas else None
    costs = [p.cost for p in profiles if p.cost > 0]
    median_cost = median(costs) if costs else None

    for p in profiles:
        insights.extend(_rules_for_profile(
            p, median_cpa=median_cpa, median_cost=median_cost,
        ))
    insights.extend(_campaign_budget_review(profiles))

    # Deterministic order: severity (HIGH first), then kind, then content_ref.
    severity_rank = {
        AdsInsightSeverity.HIGH: 0,
        AdsInsightSeverity.MEDIUM: 1,
        AdsInsightSeverity.LOW: 2,
    }
    insights.sort(
        key=lambda i: (
            severity_rank[i.severity], i.kind.value, i.content_ref or "",
        )
    )
    return insights


def _rules_for_profile(
    p: AdGroupProfile,
    *,
    median_cpa: float | None,
    median_cost: float | None,
) -> list[GoogleAdsInsight]:
    out: list[GoogleAdsInsight] = []

    # Rule 1 — high spend, zero conversions.
    if p.cost >= _HIGH_SPEND_ZERO_CONV_COST and p.conversions == 0:
        out.append(_make_insight(
            p,
            kind=AdsInsightKind.HIGH_SPEND_ZERO_CONV,
            severity=AdsInsightSeverity.HIGH,
            action=AdsInsightAction.PAUSE_CANDIDATE,
            title=f"High spend with zero conversions — {p.dimension or p.content_ref}",
            rationale=(
                f"Ad group spent {p.cost:.2f} with 0 conversions. "
                "Pause-candidate while reviewing intent + landing fit."
            ),
            thresholds={
                "min_cost": _HIGH_SPEND_ZERO_CONV_COST,
                "max_conversions": 0.0,
            },
        ))

    # Rule 2 — high spend, low conversions.
    elif (
        p.cost >= _HIGH_SPEND_LOW_CONV_COST
        and 0 < p.conversions < _HIGH_SPEND_LOW_CONV_THRESHOLD
    ):
        out.append(_make_insight(
            p,
            kind=AdsInsightKind.HIGH_SPEND_LOW_CONV,
            severity=AdsInsightSeverity.HIGH,
            action=AdsInsightAction.REVIEW_CAMPAIGN,
            title=f"High spend, few conversions — {p.dimension or p.content_ref}",
            rationale=(
                f"Ad group spent {p.cost:.2f} for {p.conversions:.1f} "
                "conversions. Review targeting + creative."
            ),
            thresholds={
                "min_cost": _HIGH_SPEND_LOW_CONV_COST,
                "max_conversions": _HIGH_SPEND_LOW_CONV_THRESHOLD,
            },
        ))

    # Rule 3 — low CTR with meaningful impressions.
    if (
        p.impressions >= _LOW_CTR_MIN_IMPR
        and p.ctr is not None
        and p.ctr < _LOW_CTR_THRESHOLD
    ):
        out.append(_make_insight(
            p,
            kind=AdsInsightKind.LOW_CTR_HIGH_IMPR,
            severity=AdsInsightSeverity.MEDIUM,
            action=AdsInsightAction.IMPROVE_AD_COPY,
            title=f"Low CTR at scale — {p.dimension or p.content_ref}",
            rationale=(
                f"CTR {p.ctr:.4f} over {p.impressions:.0f} impressions. "
                "Refresh ad copy / headlines."
            ),
            thresholds={
                "min_impressions": _LOW_CTR_MIN_IMPR,
                "max_ctr": _LOW_CTR_THRESHOLD,
            },
        ))

    # Rule 4 — good CTR but low conversion rate → landing issue.
    if (
        p.ctr is not None
        and p.ctr >= _GOOD_CTR_THRESHOLD
        and p.clicks >= _GOOD_CTR_MIN_CLICKS
        and p.conversion_rate is not None
        and p.conversion_rate < _LOW_CONV_RATE_THRESHOLD
    ):
        out.append(_make_insight(
            p,
            kind=AdsInsightKind.GOOD_CTR_LOW_CONV_RATE,
            severity=AdsInsightSeverity.MEDIUM,
            action=AdsInsightAction.REVIEW_LANDING,
            title=(
                f"Good CTR but low conversion rate — "
                f"{p.dimension or p.content_ref}"
            ),
            rationale=(
                f"CTR {p.ctr:.4f} with conversion rate "
                f"{p.conversion_rate:.4f}. Likely a landing-page issue."
            ),
            thresholds={
                "min_ctr": _GOOD_CTR_THRESHOLD,
                "min_clicks": _GOOD_CTR_MIN_CLICKS,
                "max_conv_rate": _LOW_CONV_RATE_THRESHOLD,
            },
        ))

    # Rule 5 — high CPA outlier vs snapshot median.
    if (
        median_cpa is not None
        and p.cpa is not None
        and p.conversions >= 1
        and p.cpa > median_cpa * _HIGH_CPA_MULTIPLIER
    ):
        out.append(_make_insight(
            p,
            kind=AdsInsightKind.HIGH_CPA_OUTLIER,
            severity=AdsInsightSeverity.MEDIUM,
            action=AdsInsightAction.REVIEW_AD_GROUP,
            title=f"High CPA outlier — {p.dimension or p.content_ref}",
            rationale=(
                f"CPA {p.cpa:.2f} is {p.cpa / median_cpa:.1f}× the median "
                f"({median_cpa:.2f})."
            ),
            thresholds={
                "median_cpa": median_cpa,
                "multiplier": _HIGH_CPA_MULTIPLIER,
            },
        ))

    # Rule 6 — scale candidate (efficient + still cheap).
    if (
        p.conversions >= _SCALE_MIN_CONVERSIONS
        and median_cpa is not None
        and p.cpa is not None
        and p.cpa <= median_cpa * _SCALE_CPA_RATIO
        and median_cost is not None
        and p.cost <= median_cost
    ):
        out.append(_make_insight(
            p,
            kind=AdsInsightKind.SCALE_CANDIDATE,
            severity=AdsInsightSeverity.MEDIUM,
            action=AdsInsightAction.SCALE_CANDIDATE,
            title=f"Scale candidate — {p.dimension or p.content_ref}",
            rationale=(
                f"{p.conversions:.0f} conversions at CPA {p.cpa:.2f} "
                f"(median {median_cpa:.2f}) on below-median spend. "
                "Worth scaling — operator review required."
            ),
            thresholds={
                "min_conversions": _SCALE_MIN_CONVERSIONS,
                "cpa_ratio": _SCALE_CPA_RATIO,
                "median_cpa": median_cpa,
                "median_cost": median_cost,
            },
        ))

    return out


def _campaign_budget_review(
    profiles: list[AdGroupProfile],
) -> list[GoogleAdsInsight]:
    """Campaign-level budget review — emits at most one insight per
    campaign whose total cost lands in the top quartile."""

    if not profiles:
        return []
    by_campaign: dict[str | None, dict[str, float]] = {}
    by_campaign_dim: dict[str | None, str | None] = {}
    by_campaign_sample: dict[str | None, list[AdGroupProfile]] = {}
    for p in profiles:
        agg = by_campaign.setdefault(p.campaign_id, {
            "cost": 0.0, "conversions": 0.0, "clicks": 0.0,
        })
        agg["cost"] += p.cost
        agg["conversions"] += p.conversions
        agg["clicks"] += p.clicks
        if p.campaign_id not in by_campaign_dim and p.dimension:
            # Use the campaign portion of the dimension.
            head = p.dimension.split(" / ", 1)[0]
            by_campaign_dim[p.campaign_id] = head
        by_campaign_sample.setdefault(p.campaign_id, []).append(p)

    costs = sorted([v["cost"] for v in by_campaign.values()])
    if len(costs) < 2:
        return []
    idx = max(0, int(len(costs) * _BUDGET_TOP_QUARTILE) - 1)
    cutoff = costs[idx]

    out: list[GoogleAdsInsight] = []
    for cid, agg in by_campaign.items():
        if agg["cost"] < cutoff or agg["cost"] <= 0:
            continue
        sample = by_campaign_sample[cid][0]
        out.append(GoogleAdsInsight(
            kind=AdsInsightKind.BUDGET_REVIEW,
            severity=AdsInsightSeverity.LOW,
            suggested_action=AdsInsightAction.BUDGET_REVIEW,
            title=(
                "Top-quartile spend — budget review: "
                f"{by_campaign_dim.get(cid) or f'campaign:{cid}'}"
            ),
            rationale=(
                f"Campaign aggregate cost {agg['cost']:.2f} is in the top "
                "quartile of the snapshot. Review budget allocation."
            ),
            content_ref=f"campaign:{cid}" if cid else None,
            campaign_id=cid,
            ad_group_id=None,
            dimension=by_campaign_dim.get(cid),
            evidence={
                "campaign_cost": round(agg["cost"], 2),
                "campaign_conversions": round(agg["conversions"], 2),
                "campaign_clicks": round(agg["clicks"], 2),
                "cutoff_cost": round(cutoff, 2),
            },
            thresholds_used={
                "top_quartile": _BUDGET_TOP_QUARTILE,
                "cutoff_cost": round(cutoff, 2),
            },
        ))
        # Sample is consumed only for the dimension; mark it
        # referenced to satisfy linters.
        _ = sample
    return out


# ---------- helpers ----------


def _make_insight(
    p: AdGroupProfile,
    *,
    kind: AdsInsightKind,
    severity: AdsInsightSeverity,
    action: AdsInsightAction,
    title: str,
    rationale: str,
    thresholds: dict[str, float],
) -> GoogleAdsInsight:
    return GoogleAdsInsight(
        kind=kind,
        severity=severity,
        suggested_action=action,
        title=title,
        rationale=rationale,
        content_ref=p.content_ref,
        campaign_id=p.campaign_id,
        ad_group_id=p.ad_group_id,
        dimension=p.dimension,
        evidence={
            "impressions": round(p.impressions, 2),
            "clicks": round(p.clicks, 2),
            "cost": round(p.cost, 2),
            "conversions": round(p.conversions, 2),
            "ctr": round(p.ctr, 6) if p.ctr is not None else 0.0,
            "cpa": round(p.cpa, 2) if p.cpa is not None else 0.0,
            "conversion_rate": round(p.conversion_rate, 6) if p.conversion_rate is not None else 0.0,
        },
        thresholds_used=thresholds,
    )


def _build_stats(
    *,
    profiles: list[AdGroupProfile],
    insights: Iterable[GoogleAdsInsight],
    rows: int,
) -> AdsInsightStats:
    insights_list = list(insights)
    by_severity: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for i in insights_list:
        by_severity[i.severity.value] = by_severity.get(i.severity.value, 0) + 1
        by_kind[i.kind.value] = by_kind.get(i.kind.value, 0) + 1
        by_action[i.suggested_action.value] = by_action.get(
            i.suggested_action.value, 0,
        ) + 1
    return AdsInsightStats(
        total_insights=len(insights_list),
        by_severity=by_severity,
        by_kind=by_kind,
        by_action=by_action,
        ad_groups_profiled=len(profiles),
        rows_analyzed=rows,
    )


# Re-export ``datetime`` for tests that want to monkey-patch ``utcnow``.
__all__ = [
    "DEFAULT_ADS_ANALYZER_RULE_SET_ID",
    "GoogleAdsAnalyzer",
    "analyze_and_persist_ads",
    "datetime",
]
