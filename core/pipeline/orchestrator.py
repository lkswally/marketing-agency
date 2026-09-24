"""PipelineOrchestrator — chains the five layers into a single run.

Reads a client intake JSON and walks:

1. Intake (MKT-3E): validate → normalize → persist + brief.json
2. Strategy (MKT-3A): run_from_brief → persist report + markdown
3. Approval (MKT-3B): build_from_report → persist + render markdown
4. Creative (MKT-3C): build → persist + markdown + json
5. Visual (MKT-3D): build → persist + markdown + json
6. Summary (MKT-3F): assemble CampaignRunSummary → persist + markdown + json

Each stage's outcome is recorded in :class:`StageResult`. The orchestrator
honors three flags:

- ``strict`` → halt after intake when there are critical issues (exit 4 at
  CLI level; the summary still gets written).
- ``stop_on_blocked`` → halt after approval when the pack blocks publish
  (clean exit; later stages are recorded as ``SKIPPED``).
- ``require_approval`` → fail with a typed sentinel when approval blocks
  publish (the CLI maps that to exit 3).

Determinism: same intake + same flags → same persisted artifacts (modulo
fresh ids and timestamps).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.approval import (
    APPROVAL_PACK_KIND,
    ApprovalPackBuilder,
)
from core.approval import (
    render_markdown_pack as render_approval_markdown,
)
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import (
    CREATIVE_PACK_KIND,
    CreativeFactory,
)
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.creative import (
    render_markdown_pack as render_creative_markdown,
)
from core.creative.models import CreativeAssetState
from core.domain.base import utcnow
from core.intake import (
    INTAKE_KIND,
    VALIDATION_KIND,
    ClientIntake,
    IntakeNormalizationError,
    IntakeValidator,
    normalize_intake,
    render_intake_summary,
)
from core.intake import SINGLETON_ID as INTAKE_SINGLETON
from core.memory import Memory
from core.strategy import (
    REPORT_KIND,
    BackendKind,
    StrategyBackend,
    StrategyPipeline,
    StrategyPipelineError,
)
from core.strategy import SINGLETON_ID as STRATEGY_SINGLETON
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import (
    VISUAL_PACK_KIND,
    VisualPromptFactory,
)
from core.visual import (
    render_markdown_pack as render_visual_markdown,
)

from .models import (
    PIPELINE_RUN_VERSION,
    CampaignRunSummary,
    StageId,
    StageOutcome,
    StageResult,
)
from .progress import CampaignProgressTracker
from .renderer import render_markdown_summary

PIPELINE_RUN_KIND = "campaign_run_summary"
PIPELINE_RUN_SINGLETON = "current"

DEFAULT_RULE_SET_ID = "pipeline-default.v1"


class PipelineBlockedByApproval(RuntimeError):  # noqa: N818
    """Raised when ``require_approval=True`` and the Approval Pack blocks publish.

    The CLI translates this into exit code 3.
    """


class PipelineStrictFailure(RuntimeError):  # noqa: N818
    """Raised when ``strict=True`` and the intake validator reports critical issues.

    The CLI translates this into exit code 4.
    """


class PipelineOrchestrator:
    """Chains every layer into one campaign run."""

    def __init__(
        self,
        memory: Memory,
        *,
        outputs_root: Path,
        job_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self._memory = memory
        self._outputs_root = outputs_root
        # Set per-run by run() / run_from_file(). Reset every invocation
        # so re-using the same orchestrator across runs is safe.
        self._strategy_backend: StrategyBackend | None = None
        self._backend_requested: BackendKind = BackendKind.TEMPLATED
        self._backend_fallback_events: list = []
        # MKT-11D — optional correlation metadata. Additive only: absent
        # (None) by default, so every pre-existing caller (the legacy
        # `mkt run-campaign` CLI path) emits byte-identical audit payloads
        # to before. Populated only when this orchestrator instance is
        # driven by the job system (core/jobs/operations/campaign.py).
        self._job_id = job_id
        self._correlation_id = correlation_id
        # job-execution-robustness: incremental progress checkpoint,
        # created only once client_slug is known (after intake succeeds)
        # and only when job-driven — see core/pipeline/progress.py.
        self._progress: CampaignProgressTracker | None = None

    # ---------- progress checkpoint helpers (no-op unless job-driven) ----------

    def _progress_stage_starting(self, stage: StageId) -> None:
        if self._progress is not None:
            self._progress.stage_starting(stage)

    def _progress_stage_finished(self, stage: StageId, outcome: StageOutcome) -> None:
        if self._progress is not None:
            self._progress.stage_finished(stage, outcome)

    def _progress_stages_skipped(self, stage_ids: list[StageId]) -> None:
        if self._progress is not None:
            self._progress.stages_skipped(stage_ids)

    # ---------- public API ----------

    def run(
        self,
        intake_path: Path,
        *,
        strict: bool = False,
        require_approval: bool = False,
        stop_on_blocked: bool = False,
        strategy_backend: StrategyBackend | None = None,
    ) -> CampaignRunSummary:
        started_at = utcnow()
        stages: list[StageResult] = []

        # Reset per-run backend bookkeeping.
        self._strategy_backend = strategy_backend
        self._backend_requested = (
            strategy_backend.kind if strategy_backend is not None else BackendKind.TEMPLATED
        )
        self._backend_fallback_events = []
        self._backend_invocation_records = []

        # ----- Stage 1: intake -----
        intake_result, intake, validation, brief_path = self._stage_intake(strict=strict)
        stages.append(intake_result)
        if intake_result.outcome is StageOutcome.FAILED:
            # Only raise PipelineStrictFailure when the failure was triggered
            # by --strict on a real (parseable) intake. Missing files or schema
            # errors degrade gracefully into a FAILED intake stage.
            triggered_by_strict = bool(
                strict
                and validation is not None
                and validation.missing_critical_count > 0
            )
            return self._finalize_failure(
                started_at=started_at,
                stages=stages,
                client_slug=validation.client_slug if validation else "invalid",
                intake_validation=validation,
                strict_failure=triggered_by_strict,
            )

        client_slug = validation.client_slug

        # job-execution-robustness: the checkpoint can only start once
        # client_slug is known (intake's own job is to determine it) —
        # intake's brief execution window before this point is not
        # individually checkpointed; it has no external side effects and
        # any failure there already returns via _finalize_failure above,
        # before any job-driven state exists to reconcile. Record intake
        # as already-completed the moment the tracker exists, since we
        # only reach this line when it succeeded.
        if self._job_id is not None:
            self._progress = CampaignProgressTracker(
                self._memory, job_id=self._job_id, client_slug=client_slug,
                correlation_id=self._correlation_id,
            )
            self._progress.stage_finished(StageId.INTAKE, StageOutcome.SUCCEEDED)

        # Emit "pipeline started" once we know the slug.
        self._emit_event(
            client_slug=client_slug,
            payload={
                "action": "started",
                "intake_id": validation.intake_id,
                "strict": strict,
                "require_approval": require_approval,
                "stop_on_blocked": stop_on_blocked,
                "backend_requested": self._backend_requested.value,
            },
        )

        # ----- Stage 2: strategy -----
        self._progress_stage_starting(StageId.STRATEGY)
        strategy_result, report = self._stage_strategy(client_slug, brief_path)
        stages.append(strategy_result)
        self._progress_stage_finished(StageId.STRATEGY, strategy_result.outcome)
        if strategy_result.outcome is StageOutcome.FAILED:
            return self._finalize_failure(
                started_at=started_at,
                stages=stages,
                client_slug=client_slug,
                intake_validation=validation,
            )

        # ----- Stage 3: approval -----
        self._progress_stage_starting(StageId.APPROVAL)
        approval_result, approval_pack = self._stage_approval(client_slug, report)
        stages.append(approval_result)
        self._progress_stage_finished(StageId.APPROVAL, approval_result.outcome)

        if require_approval and approval_pack.blocks_publish:
            # Record skipped stages so the summary stays well-formed, then raise.
            stages.extend(
                self._skip_stages(
                    [StageId.CREATIVE, StageId.VISUAL],
                    note="skipped because --require-approval and approval blocks publish",
                )
            )
            self._progress_stages_skipped([StageId.CREATIVE, StageId.VISUAL])
            summary = self._build_summary(
                started_at=started_at,
                stages=stages,
                client_slug=client_slug,
                intake_validation=validation,
                report=report,
                approval_pack=approval_pack,
                creative_pack=None,
                visual_pack=None,
            )
            self._persist_summary_and_render(summary)
            raise PipelineBlockedByApproval(
                f"Approval Pack blocks publish for client {client_slug!r}; "
                "creative + visual stages were skipped."
            )

        if stop_on_blocked and approval_pack.blocks_publish:
            stages.extend(
                self._skip_stages(
                    [StageId.CREATIVE, StageId.VISUAL],
                    note="skipped because --stop-on-blocked and approval blocks publish",
                )
            )
            self._progress_stages_skipped([StageId.CREATIVE, StageId.VISUAL])
            summary = self._build_summary(
                started_at=started_at,
                stages=stages,
                client_slug=client_slug,
                intake_validation=validation,
                report=report,
                approval_pack=approval_pack,
                creative_pack=None,
                visual_pack=None,
            )
            # Persist final summary so the SKIPPED creative/visual stages are
            # surfaced in campaign-final-summary.{md,json} and in memory.
            self._persist_summary_and_render(summary)
            return self._finalize_summary(summary)

        # Default: approval blocks without an explicit override flag.
        # Creative/visual stages are SKIPPED — no publish-ready outputs generated.
        # Audit trail records "approval.blocked". Exit 0 (degraded, not a crash).
        if approval_pack.blocks_publish:
            self._emit_event(
                client_slug=client_slug,
                payload={
                    "action": "approval.blocked",
                    "approval_pack_id": approval_pack.pack_id,
                    "note": (
                        "creative + visual stages skipped; "
                        "pass --stop-on-blocked (exit 0) or "
                        "--require-approval (exit 3) to make the gate explicit"
                    ),
                },
            )
            stages.extend(
                self._skip_stages(
                    [StageId.CREATIVE, StageId.VISUAL],
                    note="skipped — approval blocks publish",
                )
            )
            self._progress_stages_skipped([StageId.CREATIVE, StageId.VISUAL])
            summary = self._build_summary(
                started_at=started_at,
                stages=stages,
                client_slug=client_slug,
                intake_validation=validation,
                report=report,
                approval_pack=approval_pack,
                creative_pack=None,
                visual_pack=None,
            )
            self._persist_summary_and_render(summary)
            return self._finalize_summary(summary)

        # ----- Stage 4: creative -----
        self._progress_stage_starting(StageId.CREATIVE)
        creative_result, creative_pack = self._stage_creative(
            client_slug, report, approval_pack
        )
        stages.append(creative_result)
        self._progress_stage_finished(StageId.CREATIVE, creative_result.outcome)

        # ----- Stage 5: visual -----
        self._progress_stage_starting(StageId.VISUAL)
        visual_result, visual_pack = self._stage_visual(
            client_slug, report, approval_pack, creative_pack
        )
        stages.append(visual_result)
        self._progress_stage_finished(StageId.VISUAL, visual_result.outcome)

        # ----- Stage 6: summary -----
        self._progress_stage_starting(StageId.SUMMARY)
        summary_start = utcnow()
        summary = self._build_summary(
            started_at=started_at,
            stages=stages,
            client_slug=client_slug,
            intake_validation=validation,
            report=report,
            approval_pack=approval_pack,
            creative_pack=creative_pack,
            visual_pack=visual_pack,
        )
        # Add the summary stage itself.
        artifact_refs, memory_refs = self._persist_summary_and_render(summary)
        summary.stages.append(
            StageResult(
                stage_id=StageId.SUMMARY,
                outcome=StageOutcome.SUCCEEDED,
                started_at=summary_start,
                finished_at=utcnow(),
                artifact_refs=artifact_refs,
                memory_refs=memory_refs,
            )
        )
        # Re-finalize timestamps after appending the summary stage.
        summary.finished_at = utcnow()
        self._memory.put(
            client_slug,
            PIPELINE_RUN_KIND,
            PIPELINE_RUN_SINGLETON,
            summary.model_dump(mode="json"),
        )
        self._progress_stage_finished(StageId.SUMMARY, StageOutcome.SUCCEEDED)
        return self._finalize_summary(summary)

    # ---------- stage implementations ----------

    def _stage_intake(
        self, *, strict: bool
    ) -> tuple[StageResult, ClientIntake | None, Any, Path | None]:
        started_at = utcnow()
        try:
            raw = json.loads(self._intake_path.read_text(encoding="utf-8"))
            intake = ClientIntake.model_validate(raw)
        except Exception as e:  # noqa: BLE001
            return (
                StageResult(
                    stage_id=StageId.INTAKE,
                    outcome=StageOutcome.FAILED,
                    started_at=started_at,
                    finished_at=utcnow(),
                    notes=f"invalid intake: {e}",
                ),
                None,
                None,
                None,
            )

        validation = IntakeValidator().validate(intake)
        client_slug = validation.client_slug

        # Persist intake + validation in memory.
        self._memory.put(
            client_slug, INTAKE_KIND, INTAKE_SINGLETON, intake.model_dump(mode="json")
        )
        self._memory.put(
            client_slug,
            VALIDATION_KIND,
            INTAKE_SINGLETON,
            validation.model_dump(mode="json"),
        )

        outputs_dir = self._outputs_dir_for(client_slug)
        intake_json_path = outputs_dir / "intake.json"
        intake_json_path.write_text(intake.to_json(indent=2), encoding="utf-8")
        intake_md_path = outputs_dir / "intake-summary.md"
        intake_md_path.write_text(
            render_intake_summary(intake, validation), encoding="utf-8"
        )

        brief_path: Path | None = None
        notes: str | None = None
        outcome = StageOutcome.SUCCEEDED
        if validation.can_normalize:
            try:
                brief = normalize_intake(intake, validation)
                brief_path = outputs_dir / "brief.json"
                brief_path.write_text(brief.to_json(indent=2), encoding="utf-8")
            except IntakeNormalizationError as e:
                outcome = StageOutcome.FAILED
                notes = f"normalization failed: {e}"

        if strict and validation.missing_critical_count > 0:
            outcome = StageOutcome.FAILED
            notes = (
                f"--strict and {validation.missing_critical_count} critical issue(s) "
                "in intake"
            )

        self._emit_event(
            client_slug=client_slug,
            payload={
                "stage": StageId.INTAKE.value,
                "action": outcome.value,
                "intake_id": validation.intake_id,
            },
        )

        result = StageResult(
            stage_id=StageId.INTAKE,
            outcome=outcome,
            started_at=started_at,
            finished_at=utcnow(),
            artifact_refs=[str(intake_json_path), str(intake_md_path)]
            + ([str(brief_path)] if brief_path else []),
            memory_refs=[
                f"{INTAKE_KIND}/{INTAKE_SINGLETON}",
                f"{VALIDATION_KIND}/{INTAKE_SINGLETON}",
            ],
            notes=notes,
        )
        return result, intake, validation, brief_path

    def _stage_strategy(self, client_slug: str, brief_path: Path | None):
        started_at = utcnow()
        if brief_path is None:
            return (
                StageResult(
                    stage_id=StageId.STRATEGY,
                    outcome=StageOutcome.FAILED,
                    started_at=started_at,
                    finished_at=utcnow(),
                    notes="brief.json was not produced — intake stage did not normalize",
                ),
                None,
            )

        pipeline = StrategyPipeline(
            memory=self._memory,
            strategy_backend=self._strategy_backend,
        )
        outputs_dir = self._outputs_dir_for(client_slug)
        report_md_path = outputs_dir / "campaign-strategy.md"

        try:
            result = pipeline.run_from_path(
                brief_path, write_markdown_to=report_md_path
            )
        except StrategyPipelineError as e:
            stage = StageResult(
                stage_id=StageId.STRATEGY,
                outcome=StageOutcome.FAILED,
                started_at=started_at,
                finished_at=utcnow(),
                notes=f"strategy pipeline failed: {e}",
            )
            return stage, None

        # Collect any backend fallback events for the audit + summary.
        self._backend_fallback_events.extend(result.fallback_events)

        # Collect any invocation records (MKT-4B). Only present when a
        # ClaudeStrategyBackend with a real invoker is wired.
        sb = self._strategy_backend
        if sb is not None and hasattr(sb, "drain_invocation_records"):
            records = sb.drain_invocation_records()
            self._backend_invocation_records.extend(records)
            for rec in records:
                self._emit_event(
                    client_slug=client_slug,
                    payload={
                        "stage": StageId.STRATEGY.value,
                        "action": "strategy_backend_invocation",
                        "method": rec.method,
                        "model": rec.model,
                        "request_id": rec.request_id,
                        "input_tokens": rec.input_tokens,
                        "output_tokens": rec.output_tokens,
                        "duration_ms": rec.duration_ms,
                        "ok": rec.ok,
                        "error_type": rec.error_type,
                    },
                )

        for fb in result.fallback_events:
            self._emit_event(
                client_slug=client_slug,
                payload={
                    "stage": StageId.STRATEGY.value,
                    "action": "strategy_backend_fallback",
                    "method": fb.method,
                    "requested_backend": fb.requested_backend.value,
                    "fallback_backend": fb.fallback_backend.value,
                    "reason": fb.reason,
                },
            )

        notes = None
        if result.fallback_events:
            notes = (
                f"strategy backend fallback x{len(result.fallback_events)}: "
                + ", ".join(fb.method for fb in result.fallback_events)
            )

        self._emit_event(
            client_slug=client_slug,
            payload={
                "stage": StageId.STRATEGY.value,
                "action": "succeeded",
                "report_id": result.report.report_id,
                "backend_requested": self._backend_requested.value,
                "fallback_count": len(result.fallback_events),
            },
        )
        stage = StageResult(
            stage_id=StageId.STRATEGY,
            outcome=StageOutcome.SUCCEEDED,
            started_at=started_at,
            finished_at=utcnow(),
            artifact_refs=[str(report_md_path)],
            memory_refs=[f"{REPORT_KIND}/{STRATEGY_SINGLETON}"],
            notes=notes,
        )
        return stage, result.report

    def _stage_approval(self, client_slug: str, report):
        started_at = utcnow()
        builder = ApprovalPackBuilder(memory=self._memory)
        # MKT-11E: every run builds and persists a NEW approval (fresh
        # pack_id) — never overwrites a prior approval for this client.
        # job_id/correlation_id are threaded through only when this
        # orchestrator instance is driven by the job system.
        pack = builder.build_from_report(
            report, job_id=self._job_id, correlation_id=self._correlation_id,
        )
        builder.persist(pack)

        outputs_dir = self._outputs_dir_for(client_slug)
        md_path = outputs_dir / "approval-pack.md"
        md_path.write_text(render_approval_markdown(pack), encoding="utf-8")
        json_path = outputs_dir / "approval-pack.json"
        json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

        outcome = (
            StageOutcome.BLOCKED if pack.blocks_publish else StageOutcome.SUCCEEDED
        )
        self._emit_event(
            client_slug=client_slug,
            payload={
                "stage": StageId.APPROVAL.value,
                "action": outcome.value,
                "approval_pack_id": pack.pack_id,
                "blocks_publish": pack.blocks_publish,
            },
        )
        stage = StageResult(
            stage_id=StageId.APPROVAL,
            outcome=outcome,
            started_at=started_at,
            finished_at=utcnow(),
            artifact_refs=[str(md_path), str(json_path)],
            memory_refs=[f"{APPROVAL_PACK_KIND}/{pack.pack_id}"],
        )
        return stage, pack

    def _stage_creative(self, client_slug: str, report, approval_pack):
        started_at = utcnow()
        factory = CreativeFactory(memory=self._memory)
        pack = factory.build(report, approval_pack)
        factory.persist(pack)

        outputs_dir = self._outputs_dir_for(client_slug)
        md_path = outputs_dir / "creative-pack.md"
        md_path.write_text(render_creative_markdown(pack), encoding="utf-8")
        json_path = outputs_dir / "creative-pack.json"
        json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

        self._emit_event(
            client_slug=client_slug,
            payload={
                "stage": StageId.CREATIVE.value,
                "action": "succeeded",
                "creative_pack_id": pack.pack_id,
            },
        )
        stage = StageResult(
            stage_id=StageId.CREATIVE,
            outcome=StageOutcome.SUCCEEDED,
            started_at=started_at,
            finished_at=utcnow(),
            artifact_refs=[str(md_path), str(json_path)],
            memory_refs=[f"{CREATIVE_PACK_KIND}/{CREATIVE_SINGLETON}"],
        )
        return stage, pack

    def _stage_visual(self, client_slug: str, report, approval_pack, creative_pack):
        started_at = utcnow()
        factory = VisualPromptFactory(memory=self._memory)
        pack = factory.build(report, approval_pack, creative_pack)
        factory.persist(pack)

        outputs_dir = self._outputs_dir_for(client_slug)
        md_path = outputs_dir / "visual-direction-pack.md"
        md_path.write_text(render_visual_markdown(pack), encoding="utf-8")
        json_path = outputs_dir / "visual-direction-pack.json"
        json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

        self._emit_event(
            client_slug=client_slug,
            payload={
                "stage": StageId.VISUAL.value,
                "action": "succeeded",
                "visual_pack_id": pack.pack_id,
            },
        )
        stage = StageResult(
            stage_id=StageId.VISUAL,
            outcome=StageOutcome.SUCCEEDED,
            started_at=started_at,
            finished_at=utcnow(),
            artifact_refs=[str(md_path), str(json_path)],
            memory_refs=[f"{VISUAL_PACK_KIND}/{VISUAL_SINGLETON}"],
        )
        return stage, pack

    # ---------- helpers ----------

    @property
    def _intake_path(self) -> Path:
        return self._current_intake_path

    def run_from_file(
        self,
        intake_path: Path,
        *,
        strict: bool = False,
        require_approval: bool = False,
        stop_on_blocked: bool = False,
        strategy_backend: StrategyBackend | None = None,
    ) -> CampaignRunSummary:
        """Public entrypoint — caller supplies the intake path directly."""
        self._current_intake_path = intake_path
        return self.run(
            intake_path,
            strict=strict,
            require_approval=require_approval,
            stop_on_blocked=stop_on_blocked,
            strategy_backend=strategy_backend,
        )

    def _outputs_dir_for(self, client_slug: str) -> Path:
        d = self._outputs_root / client_slug
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _skip_stages(
        self, stage_ids: list[StageId], *, note: str
    ) -> list[StageResult]:
        now = utcnow()
        out: list[StageResult] = []
        for sid in stage_ids:
            out.append(
                StageResult(
                    stage_id=sid,
                    outcome=StageOutcome.SKIPPED,
                    started_at=now,
                    finished_at=now,
                    notes=note,
                )
            )
        return out

    def _build_summary(
        self,
        *,
        started_at: datetime,
        stages: list[StageResult],
        client_slug: str,
        intake_validation,
        report=None,
        approval_pack=None,
        creative_pack=None,
        visual_pack=None,
    ) -> CampaignRunSummary:
        overall_state = self._compute_overall_state(approval_pack)
        blocks_publish = (
            approval_pack.blocks_publish if approval_pack is not None else False
        )
        # Backend bookkeeping.
        backend_requested = self._backend_requested.value
        fb_events = self._backend_fallback_events
        fb_count = len(fb_events)
        if self._strategy_backend is None or fb_count == 0:
            # No backend injected, or no fallbacks: effective == requested.
            backend_effective = backend_requested
        else:
            # We requested Claude; some calls fell back to templated.
            # There are six "creative" methods total. All fell back → templated.
            # Some fell back → mixed.
            backend_effective = (
                "templated" if fb_count >= 6 else "mixed"
            )
        fb_notes = [f"{fb.method}: {fb.reason}" for fb in fb_events]

        return CampaignRunSummary(
            contract_version=PIPELINE_RUN_VERSION,
            client_slug=client_slug,
            started_at=started_at,
            finished_at=utcnow(),
            intake_id=intake_validation.intake_id if intake_validation else None,
            validation_id=intake_validation.intake_id if intake_validation else None,
            brief_path=next(
                (
                    a
                    for s in stages
                    if s.stage_id is StageId.INTAKE
                    for a in s.artifact_refs
                    if a.endswith("brief.json")
                ),
                None,
            ),
            report_id=report.report_id if report else None,
            approval_pack_id=approval_pack.pack_id if approval_pack else None,
            creative_pack_id=creative_pack.pack_id if creative_pack else None,
            visual_pack_id=visual_pack.pack_id if visual_pack else None,
            overall_state=overall_state,
            blocks_publish=blocks_publish,
            intake_critical_count=intake_validation.missing_critical_count if intake_validation else 0,
            intake_warning_count=intake_validation.missing_warning_count if intake_validation else 0,
            intake_info_count=intake_validation.missing_info_count if intake_validation else 0,
            stages=list(stages),
            rule_set_id=DEFAULT_RULE_SET_ID,
            backend_requested=backend_requested,
            backend_effective=backend_effective,
            backend_fallback_count=fb_count,
            backend_fallback_notes=fb_notes,
            claude_invocations=list(self._backend_invocation_records),
        )

    def _compute_overall_state(self, approval_pack) -> CreativeAssetState:
        if approval_pack is None:
            return CreativeAssetState.NEEDS_REVIEW
        if approval_pack.blocks_publish:
            return CreativeAssetState.BLOCKED
        # Mirror the derivation used by the creative/visual factories.
        from core.approval.models import ApprovalState

        if approval_pack.state is ApprovalState.APPROVED:
            return CreativeAssetState.READY_FOR_PUBLISH
        return CreativeAssetState.DRAFT

    def _persist_summary_and_render(
        self, summary: CampaignRunSummary
    ) -> tuple[list[str], list[str]]:
        outputs_dir = self._outputs_dir_for(summary.client_slug)
        md_path = outputs_dir / "campaign-final-summary.md"
        md_path.write_text(render_markdown_summary(summary), encoding="utf-8")
        json_path = outputs_dir / "campaign-final-summary.json"
        json_path.write_text(summary.to_json(indent=2), encoding="utf-8")
        self._memory.put(
            summary.client_slug,
            PIPELINE_RUN_KIND,
            PIPELINE_RUN_SINGLETON,
            summary.model_dump(mode="json"),
        )
        return (
            [str(md_path), str(json_path)],
            [f"{PIPELINE_RUN_KIND}/{PIPELINE_RUN_SINGLETON}"],
        )

    def _finalize_summary(self, summary: CampaignRunSummary) -> CampaignRunSummary:
        self._emit_event(
            client_slug=summary.client_slug,
            payload={
                "action": "finished",
                "run_id": summary.run_id,
                "overall_state": summary.overall_state.value,
                "blocks_publish": summary.blocks_publish,
                "stages_total": len(summary.stages),
                "backend_requested": summary.backend_requested,
                "backend_effective": summary.backend_effective,
                "backend_fallback_count": summary.backend_fallback_count,
            },
        )
        return summary

    def _finalize_failure(
        self,
        *,
        started_at: datetime,
        stages: list[StageResult],
        client_slug: str,
        intake_validation,
        strict_failure: bool = False,
    ) -> CampaignRunSummary:
        # When intake itself fails, no client_slug is reliable. Use a fallback
        # so the summary remains constructible.
        slug = client_slug if client_slug else "invalid"
        summary = self._build_summary(
            started_at=started_at,
            stages=stages,
            client_slug=slug,
            intake_validation=intake_validation,
        )
        if slug != "invalid":
            # Only persist when the slug is real.
            self._persist_summary_and_render(summary)
            self._finalize_summary(summary)
        if strict_failure:
            raise PipelineStrictFailure(
                "intake validation failed under --strict; pipeline halted."
            )
        return summary

    def _emit_event(self, *, client_slug: str, payload: dict[str, Any]) -> None:
        # MKT-11D — attach job/correlation metadata only when present, so
        # a legacy (non-job) run's payload shape is byte-identical to
        # before this field existed.
        enriched = dict(payload)
        if self._job_id is not None:
            enriched["job_id"] = self._job_id
        if self._correlation_id is not None:
            enriched["correlation_id"] = self._correlation_id
        # job-execution-robustness: atomic — this orchestrator can be
        # job-driven, and the owning job's own audit events (jobs/runner.py)
        # write to the same client's chain; build+append inside one lock.
        self._memory.append_audit_event_atomic(
            client_slug,
            lambda prev: AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor="pipeline_orchestrator",
                occurred_at=utcnow(),
                client_slug=client_slug,
                payload={"campaign_pipeline": enriched},
                prev_hash=prev,
            ),
        )


__all__ = [
    "PIPELINE_RUN_KIND",
    "PIPELINE_RUN_SINGLETON",
    "DEFAULT_RULE_SET_ID",
    "PipelineOrchestrator",
    "PipelineBlockedByApproval",
    "PipelineStrictFailure",
]
