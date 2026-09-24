"""Google Ads analysis + feedback-bridge application services
(architecture/application-service-boundary, batch 3).

Migrates ``mkt ads-analyze`` and ``mkt ads-feedback``. Kept in one
module — not one file per command — because the domain is one tightly
coupled pipeline stage: :func:`build_ads_feedback` requires
:func:`analyze_ads`'s persisted output (a :class:`GoogleAdsInsightPack`)
and raises the exact same shape of "run the other command first" error
that ``analyze_ads`` itself raises for a missing ``MetricsSnapshot``.

**Evidence boundary (Phase 4).** Neither service invents a number.
``GoogleAdsAnalyzer.analyze`` reads real, previously-persisted
``MetricRow`` entries (``MetricSource.GOOGLE_ADS`` — themselves the
product of a real ``mkt import-metrics`` file import or a real
``mkt analytics-fetch`` connector call, never fabricated here) and
applies deterministic threshold rules over them (cost, CTR, CPA,
conversion rate — all arithmetic on stored values). Classified:
PERSISTED_METRIC. ``AdsFeedbackBridge.build`` performs a pure
1-to-1/1-to-many structural translation of that same
``GoogleAdsInsightPack`` into recommendations/adjustments/tasks — it
introduces no new numeric claim (no ROAS, no conversion lift, no
revenue impact) anywhere. Its only other reads are OPTIONAL, read-only,
best-effort cross-reference lookups (``campaign_feedback_pack``,
``campaign_execution_task_pack``, ``next_campaign_iteration_plan`` —
recorded by id only, `None` when absent, never required).

**No external call, no mutation (Phase 11).** Neither domain class
touches the network, the Google Ads SDK, or any remote state — both are
pure reads over already-persisted local entities plus one write of
their own output pack. This service layer adds no new capability here;
it only relocates where the CLI's ``JsonFileMemory``/class construction
happens.
"""

from __future__ import annotations

from core.ads_analysis import GoogleAdsAnalyzer, render_markdown_ads_insights
from core.ads_feedback import AdsFeedbackBridge, render_markdown_ads_bridge
from core.memory import JsonFileMemory

from ..artifacts import OutputLayout, write_artifacts
from ..context import OperationContext
from ..result import ErrorCode, OperationResult

_ANALYZE_MD_FILENAME = "google-ads-insight-pack.md"
_ANALYZE_JSON_FILENAME = "google-ads-insight-pack.json"
_FEEDBACK_MD_FILENAME = "ads-feedback-bridge-pack.md"
_FEEDBACK_JSON_FILENAME = "ads-feedback-bridge-pack.json"


def analyze_ads(ctx: OperationContext) -> OperationResult:
    """Analyze the persisted Google Ads metric rows for
    ``ctx.client_slug`` and persist + write the resulting
    :class:`GoogleAdsInsightPack`."""
    memory = JsonFileMemory(ctx.root)
    analyzer = GoogleAdsAnalyzer(memory=memory)
    try:
        pack = analyzer.analyze(ctx.client_slug)
    except ValueError as e:
        return OperationResult.error_result(code=ErrorCode.NOT_FOUND, message=str(e))
    analyzer.persist(pack)

    files = {
        _ANALYZE_MD_FILENAME: render_markdown_ads_insights(pack),
        _ANALYZE_JSON_FILENAME: pack.to_json(indent=2),
    }
    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
        files=files,
        overwrite=True,
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code, message=write_err.message, remediation=write_err.remediation,
        )

    return OperationResult.ok_result(data=pack, artifacts=artifacts)


def build_ads_feedback(ctx: OperationContext) -> OperationResult:
    """Bridge the persisted :class:`GoogleAdsInsightPack` for
    ``ctx.client_slug`` into an :class:`AdsFeedbackBridgePack`, persist
    it, and write the Markdown + JSON report."""
    memory = JsonFileMemory(ctx.root)
    bridge = AdsFeedbackBridge(memory=memory)
    try:
        pack = bridge.build(ctx.client_slug)
    except ValueError as e:
        return OperationResult.error_result(code=ErrorCode.NOT_FOUND, message=str(e))
    bridge.persist(pack)

    files = {
        _FEEDBACK_MD_FILENAME: render_markdown_ads_bridge(pack),
        _FEEDBACK_JSON_FILENAME: pack.to_json(indent=2),
    }
    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
        files=files,
        overwrite=True,
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code, message=write_err.message, remediation=write_err.remediation,
        )

    return OperationResult.ok_result(data=pack, artifacts=artifacts)


__all__ = ["analyze_ads", "build_ads_feedback"]
