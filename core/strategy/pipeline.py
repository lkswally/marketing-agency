"""High-level orchestration for the campaign strategy engine.

``StrategyPipeline`` is the entry point used by ``mkt run-strategy``:

1. Load the input brief JSON.
2. Validate against :class:`StrategyInputBrief`.
3. Persist the brief to :class:`JsonFileMemory`.
4. Run W7 with :class:`TemplatedStrategyBackend`.
5. Read the final :class:`CampaignStrategyReport` from memory.
6. (Optionally) render and write the Markdown report.

The pipeline is the same surface the CLI consumes and what tests exercise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.contracts import WorkflowRunStatus, WorkflowRunSummary
from core.memory import Memory
from core.runtime import MinimalDispatcher
from core.workflows import WorkflowSpec, load_workflow

from .backend import (
    REPORT_KIND,
    SINGLETON_ID,
    W7TemplatedAgentBackend,
    load_input_brief_from_file,
    persist_input_brief,
)
from .backends import BackendFallbackEvent, StrategyBackend
from .models import CampaignStrategyReport, StrategyInputBrief
from .renderer import render_markdown_report

DEFAULT_WORKFLOW_PATH = Path("workflows/W7_campaign_strategy_engine.yaml")


@dataclass(frozen=True)
class StrategyRunResult:
    """What the pipeline returns to its caller."""

    summary: WorkflowRunSummary
    report: CampaignStrategyReport
    report_markdown_path: Path | None
    fallback_events: tuple[BackendFallbackEvent, ...] = ()
    """Fallback events recorded by the strategy backend during the run.
    Always empty when using :class:`TemplatedStrategyBackend`. May be
    non-empty (one entry per fallback) when using
    :class:`ClaudeStrategyBackend` with an invoker that errors or
    returns invalid output."""


class StrategyPipeline:
    """End-to-end campaign strategy execution."""

    def __init__(
        self,
        memory: Memory,
        *,
        workflow_path: Path | None = None,
        strategy_backend: StrategyBackend | None = None,
    ) -> None:
        self._memory = memory
        self._workflow_path = workflow_path or DEFAULT_WORKFLOW_PATH
        self._strategy_backend = strategy_backend

    def _load_workflow(self) -> WorkflowSpec:
        return load_workflow(self._workflow_path)

    def run_from_path(
        self,
        brief_path: Path | str,
        *,
        write_markdown_to: Path | None = None,
    ) -> StrategyRunResult:
        """Run the strategy engine using a brief JSON loaded from disk."""
        brief = load_input_brief_from_file(brief_path)
        return self.run_from_brief(brief, write_markdown_to=write_markdown_to)

    def run_from_brief(
        self,
        brief: StrategyInputBrief,
        *,
        write_markdown_to: Path | None = None,
    ) -> StrategyRunResult:
        """Run the strategy engine using an already-validated brief."""
        client_slug = brief.client.slug
        persist_input_brief(self._memory, brief)

        spec = self._load_workflow()
        # Optionally let the ClaudeStrategyBackend know which tenant it serves
        # (the invoker may scope rate-limits per-tenant).
        sb = self._strategy_backend
        if sb is not None and hasattr(sb, "set_client_slug"):
            sb.set_client_slug(client_slug)
        backend = W7TemplatedAgentBackend(self._memory, strategy_backend=sb)
        dispatcher = MinimalDispatcher(memory=self._memory, agent_backend=backend)
        summary = dispatcher.run(spec, client_slug=client_slug)

        if summary.status is not WorkflowRunStatus.SUCCEEDED:
            raise StrategyPipelineError(
                f"strategy workflow failed: status={summary.status.value}; "
                f"steps={[s.step_id for s in summary.steps]}"
            )

        report_raw = self._memory.get(client_slug, REPORT_KIND, SINGLETON_ID)
        report = CampaignStrategyReport.model_validate(report_raw)

        markdown_path: Path | None = None
        if write_markdown_to is not None:
            markdown_path = Path(write_markdown_to)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(
                render_markdown_report(report), encoding="utf-8"
            )

        fallback_events = ()
        if sb is not None and hasattr(sb, "drain_fallback_events"):
            fallback_events = tuple(sb.drain_fallback_events())

        return StrategyRunResult(
            summary=summary,
            report=report,
            report_markdown_path=markdown_path,
            fallback_events=fallback_events,
        )


class StrategyPipelineError(RuntimeError):
    """Raised when the strategy workflow ends in a non-succeeded state."""


__all__ = [
    "StrategyPipeline",
    "StrategyRunResult",
    "StrategyPipelineError",
    "DEFAULT_WORKFLOW_PATH",
]
