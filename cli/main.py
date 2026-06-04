"""``mkt`` CLI entry point.

Subcommands (MKT-2A):

    mkt list-workflows
    mkt validate-specs
    mkt memory inspect [--client <slug>] [--root <path>]
    mkt run-mock <workflow_id> --client <slug> [--root <path>]

Designed to be tested by calling :func:`main` with an explicit ``argv``.
Returns an integer suitable as a process exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from core.runtime import MinimalDispatcher, MockAgentBackend
from core.workflows import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_SKILLS_DIR,
    DEFAULT_WORKFLOWS_DIR,
    WorkflowLoadError,
    lint_all,
    load_all_workflows,
    load_workflow,
)

DEFAULT_DATA_ROOT = Path("data/clients")


# -------- subcommand implementations --------

def _cmd_list_workflows(args: argparse.Namespace, *, out) -> int:
    workflows_dir = Path(args.workflows_dir)
    try:
        specs = load_all_workflows(workflows_dir)
    except WorkflowLoadError as e:
        print(f"error: {e}", file=out)
        return 2
    if not specs:
        print(f"(no workflows found under {workflows_dir})", file=out)
        return 0
    for s in specs:
        first_line = s.description.strip().splitlines()[0] if s.description else ""
        print(f"{s.workflow_id}\tv{s.version}\t{first_line}", file=out)
    return 0


def _cmd_validate_specs(args: argparse.Namespace, *, out) -> int:
    findings = lint_all(
        workflows_dir=Path(args.workflows_dir),
        agents_dir=Path(args.agents_dir),
        skills_dir=Path(args.skills_dir),
    )
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    for f in findings:
        print(
            f"[{f.severity.upper()}] {f.rule} @ {f.target}: {f.message}",
            file=out,
        )
    print(
        f"summary: {len(errors)} error(s), {len(warnings)} warning(s)",
        file=out,
    )
    return 1 if errors else 0


def _cmd_memory_inspect(args: argparse.Namespace, *, out) -> int:
    root = Path(args.root)
    if not root.exists():
        print(f"(no memory root at {root})", file=out)
        return 0

    if args.client:
        client_dir = root / args.client
        if not client_dir.exists():
            print(f"(no client folder at {client_dir})", file=out)
            return 0
        print(f"client: {args.client}", file=out)
        for kind_dir in sorted(p for p in client_dir.iterdir() if p.is_dir()):
            if kind_dir.name == "audit":
                lines = 0
                for f in kind_dir.glob("*.jsonl"):
                    with f.open("r", encoding="utf-8") as fh:
                        lines += sum(1 for _ in fh)
                print(f"  audit/ : {lines} event(s)", file=out)
            else:
                count = sum(1 for _ in kind_dir.glob("*.json"))
                print(f"  {kind_dir.name}/ : {count}", file=out)
        return 0

    # No --client: list known clients.
    clients = sorted(p.name for p in root.iterdir() if p.is_dir())
    if not clients:
        print("(no clients persisted)", file=out)
        return 0
    print("clients:", file=out)
    for c in clients:
        print(f"  - {c}", file=out)
    return 0


def _cmd_run_mock(args: argparse.Namespace, *, out) -> int:
    # Find the requested workflow id under workflows_dir.
    workflows_dir = Path(args.workflows_dir)
    candidate = workflows_dir / f"{args.workflow_id}.yaml"
    if not candidate.exists():
        # Fallback: scan and try id match (in case file name differs).
        try:
            specs = load_all_workflows(workflows_dir)
        except WorkflowLoadError as e:
            print(f"error: {e}", file=out)
            return 2
        match = [s for s in specs if s.workflow_id == args.workflow_id]
        if not match:
            print(
                f"error: workflow_id {args.workflow_id!r} not found under {workflows_dir}",
                file=out,
            )
            return 2
        spec = match[0]
    else:
        try:
            spec = load_workflow(candidate)
        except WorkflowLoadError as e:
            print(f"error: {e}", file=out)
            return 2

    # Build memory + dispatcher.
    from core.memory import JsonFileMemory  # imported lazily to keep CLI fast

    memory = JsonFileMemory(Path(args.root))
    dispatcher = MinimalDispatcher(memory=memory, agent_backend=MockAgentBackend())
    summary = dispatcher.run(spec, client_slug=args.client)
    print(json.dumps(summary.model_dump(mode="json"), indent=2, default=str), file=out)
    return 0 if summary.status.value == "succeeded" else 1


def _cmd_run_strategy(args: argparse.Namespace, *, out) -> int:
    """Run W7 (campaign strategy engine) against an input brief.

    Output:
    - persists every intermediate strategy artifact to JsonFileMemory.
    - writes the final Markdown report to ``--outputs-dir/<client>/<filename>``.
    - prints a small JSON summary to stdout.
    """
    from core.memory import JsonFileMemory
    from core.strategy import StrategyPipeline, StrategyPipelineError

    brief_path = Path(args.brief)
    if not brief_path.exists():
        print(f"error: brief file not found: {brief_path}", file=out)
        return 2

    memory = JsonFileMemory(Path(args.root))
    pipeline = StrategyPipeline(memory=memory)

    outputs_dir = Path(args.outputs_dir)
    report_path = outputs_dir / "campaign-strategy.md"

    try:
        result = pipeline.run_from_path(brief_path, write_markdown_to=report_path)
    except StrategyPipelineError as e:
        print(f"error: {e}", file=out)
        return 1
    except Exception as e:  # noqa: BLE001 — surface validation errors as exit-2
        print(f"error: invalid brief: {e}", file=out)
        return 2

    payload = {
        "status": result.summary.status.value,
        "run_id": result.summary.run_id,
        "report_id": result.report.report_id,
        "client_slug": result.report.client_slug,
        "report_markdown_path": str(result.report_markdown_path)
        if result.report_markdown_path
        else None,
        "envelope_count": len(result.summary.envelope_refs),
    }

    # Optional chained audit + approval pack generation.
    if getattr(args, "audit", False):
        audit_payload = _do_audit_pack(
            memory=memory,
            client_slug=result.report.client_slug,
            report=result.report,
            outputs_dir=outputs_dir,
        )
        payload["approval_pack"] = audit_payload

    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _do_audit_pack(*, memory, client_slug, report, outputs_dir: Path) -> dict:
    """Internal helper used by `run-strategy --audit` and `audit-strategy`."""
    from core.approval import ApprovalPackBuilder, render_markdown_pack

    builder = ApprovalPackBuilder(memory=memory)
    pack = builder.build_from_report(report)
    builder.persist(pack)

    pack_md_path = outputs_dir / "approval-pack.md"
    pack_md_path.parent.mkdir(parents=True, exist_ok=True)
    pack_md_path.write_text(render_markdown_pack(pack), encoding="utf-8")

    return {
        "pack_id": pack.pack_id,
        "state": pack.state.value,
        "overall_severity": pack.overall_severity.value,
        "blocks_publish": pack.blocks_publish,
        "total_detections": pack.total_detections,
        "human_review_required_count": pack.human_review_required_count,
        "pack_markdown_path": str(pack_md_path),
        "client_slug": client_slug,
        "report_id": report.report_id,
        "rule_set_id": pack.rule_set_id,
    }


def _cmd_audit_strategy(args: argparse.Namespace, *, out) -> int:
    """Audit a previously-persisted CampaignStrategyReport.

    Loads the strategy report for ``--client`` from memory, builds the
    :class:`ApprovalPack`, persists it, and writes the Markdown rendering
    to ``--outputs-dir``.
    """
    from core.memory import EntityNotFound, JsonFileMemory
    from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport

    memory = JsonFileMemory(Path(args.root))
    try:
        raw = memory.get(args.client, REPORT_KIND, SINGLETON_ID)
    except EntityNotFound:
        print(
            f"error: no CampaignStrategyReport for client {args.client!r} "
            f"under {args.root}; run `mkt run-strategy` first.",
            file=out,
        )
        return 2

    report = CampaignStrategyReport.model_validate(raw)
    outputs_dir = Path(args.outputs_dir)

    audit_payload = _do_audit_pack(
        memory=memory,
        client_slug=args.client,
        report=report,
        outputs_dir=outputs_dir,
    )
    print(json.dumps(audit_payload, indent=2, default=str), file=out)
    return 0


def _cmd_build_creatives(args: argparse.Namespace, *, out) -> int:
    """Build a Creative Asset Pack from a persisted strategy + optional approval.

    Loads the persisted ``CampaignStrategyReport`` for ``--client`` and (if
    present) the latest ``ApprovalPack``, runs the :class:`CreativeFactory`,
    persists the resulting ``CreativeAssetPack`` to memory and writes
    Markdown + JSON to ``--outputs-dir``.
    """
    from core.approval import (
        APPROVAL_PACK_KIND,
        ApprovalPack,
    )
    from core.approval import SINGLETON_ID as APPROVAL_SINGLETON_ID
    from core.creative import (
        CreativeFactory,
        render_markdown_pack,
    )
    from core.memory import EntityNotFound, JsonFileMemory
    from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport

    memory = JsonFileMemory(Path(args.root))
    try:
        report_raw = memory.get(args.client, REPORT_KIND, SINGLETON_ID)
    except EntityNotFound:
        print(
            f"error: no CampaignStrategyReport for client {args.client!r} "
            f"under {args.root}; run `mkt run-strategy` first.",
            file=out,
        )
        return 2
    report = CampaignStrategyReport.model_validate(report_raw)

    approval_pack: ApprovalPack | None = None
    try:
        ap_raw = memory.get(args.client, APPROVAL_PACK_KIND, APPROVAL_SINGLETON_ID)
        approval_pack = ApprovalPack.model_validate(ap_raw)
    except EntityNotFound:
        # No audit ran yet — the factory defaults to a conservative state.
        approval_pack = None

    if (
        getattr(args, "require_approval", False)
        and approval_pack is not None
        and approval_pack.blocks_publish
    ):
        print(
            "error: --require-approval set but the Approval Pack blocks publish",
            file=out,
        )
        return 3

    factory = CreativeFactory(memory=memory)
    pack = factory.build(report, approval_pack)
    factory.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "creative-pack.md"
    md_path.write_text(render_markdown_pack(pack), encoding="utf-8")
    json_path = outputs_dir / "creative-pack.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "report_id": pack.report_id,
        "approval_pack_id": pack.approval_pack_id,
        "derived_overall_state": pack.derived_overall_state.value,
        "blocks_publish": pack.blocks_publish,
        "total_assets": pack.total_assets,
        "count_by_kind": pack.count_by_kind(),
        "count_by_state": pack.count_by_state(),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_build_visuals(args: argparse.Namespace, *, out) -> int:
    """Build a Visual Direction Pack from the persisted strategy + creative pack.

    Loads the persisted ``CampaignStrategyReport``, the latest ``ApprovalPack``
    and the latest ``CreativeAssetPack`` (when present). Runs the
    :class:`VisualPromptFactory`, persists the resulting ``VisualDirectionPack``
    to memory and writes Markdown + JSON to ``--outputs-dir``.
    """
    from core.approval import (
        APPROVAL_PACK_KIND,
        ApprovalPack,
    )
    from core.approval import SINGLETON_ID as APPROVAL_SINGLETON_ID
    from core.creative import (
        CREATIVE_PACK_KIND,
        CreativeAssetPack,
    )
    from core.creative import SINGLETON_ID as CREATIVE_SINGLETON_ID
    from core.memory import EntityNotFound, JsonFileMemory
    from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport
    from core.visual import VisualPromptFactory, render_markdown_pack

    memory = JsonFileMemory(Path(args.root))
    try:
        report_raw = memory.get(args.client, REPORT_KIND, SINGLETON_ID)
    except EntityNotFound:
        print(
            f"error: no CampaignStrategyReport for client {args.client!r} "
            f"under {args.root}; run `mkt run-strategy` first.",
            file=out,
        )
        return 2
    report = CampaignStrategyReport.model_validate(report_raw)

    approval_pack: ApprovalPack | None = None
    try:
        ap_raw = memory.get(args.client, APPROVAL_PACK_KIND, APPROVAL_SINGLETON_ID)
        approval_pack = ApprovalPack.model_validate(ap_raw)
    except EntityNotFound:
        approval_pack = None

    creative_pack: CreativeAssetPack | None = None
    try:
        cp_raw = memory.get(args.client, CREATIVE_PACK_KIND, CREATIVE_SINGLETON_ID)
        creative_pack = CreativeAssetPack.model_validate(cp_raw)
    except EntityNotFound:
        creative_pack = None

    if (
        getattr(args, "require_approval", False)
        and approval_pack is not None
        and approval_pack.blocks_publish
    ):
        print(
            "error: --require-approval set but the Approval Pack blocks publish",
            file=out,
        )
        return 3

    factory = VisualPromptFactory(memory=memory)
    pack = factory.build(report, approval_pack, creative_pack)
    factory.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "visual-direction-pack.md"
    md_path.write_text(render_markdown_pack(pack), encoding="utf-8")
    json_path = outputs_dir / "visual-direction-pack.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "report_id": pack.report_id,
        "approval_pack_id": pack.approval_pack_id,
        "creative_pack_id": pack.creative_pack_id,
        "derived_overall_state": pack.derived_overall_state.value,
        "blocks_publish": pack.blocks_publish,
        "total_directions": pack.total_directions,
        "total_prompt_variants": pack.total_prompt_variants,
        "count_by_state": pack.count_by_state(),
        "count_risks_by_severity": pack.count_risks_by_severity(),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_build_tasks(args: argparse.Namespace, *, out) -> int:
    """Build a CampaignExecutionTaskPack (MKT-4E) from persisted artifacts.

    Reads the CampaignStrategyReport (required), and optionally the
    ApprovalPack, CreativeAssetPack, and VisualDirectionPack from
    Memory under ``--client <slug>``. Builds the task pack, persists
    it to Memory, writes Markdown + JSON + Notion-payload JSON to
    ``--outputs-dir``, and prints a small JSON summary.

    Exit codes:
    - 0 on success
    - 2 when the strategy report is missing for ``--client``
    """
    import contextlib

    from core.approval import APPROVAL_PACK_KIND, ApprovalPack
    from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
    from core.contracts import AuditEventType, AuditTrailEvent
    from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
    from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
    from core.domain.base import utcnow as _utcnow
    from core.execution import (
        TaskFactory,
        render_markdown_pack,
        to_notion_payload,
    )
    from core.memory import EntityNotFound, JsonFileMemory
    from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport
    from core.visual import SINGLETON_ID as VISUAL_SINGLETON
    from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

    memory = JsonFileMemory(Path(args.root))

    try:
        report_raw = memory.get(args.client, REPORT_KIND, SINGLETON_ID)
    except EntityNotFound:
        print(
            f"error: no CampaignStrategyReport for client {args.client!r} "
            f"under {args.root}; run `mkt run-strategy` first.",
            file=out,
        )
        return 2
    report = CampaignStrategyReport.model_validate(report_raw)

    approval = None
    with contextlib.suppress(EntityNotFound):
        approval = ApprovalPack.model_validate(
            memory.get(args.client, APPROVAL_PACK_KIND, APPROVAL_SINGLETON)
        )

    creative = None
    with contextlib.suppress(EntityNotFound):
        creative = CreativeAssetPack.model_validate(
            memory.get(args.client, CREATIVE_PACK_KIND, CREATIVE_SINGLETON)
        )

    visual = None
    with contextlib.suppress(EntityNotFound):
        visual = VisualDirectionPack.model_validate(
            memory.get(args.client, VISUAL_PACK_KIND, VISUAL_SINGLETON)
        )

    factory = TaskFactory(memory=memory)
    pack = factory.build(report, approval, creative, visual)
    factory.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "campaign-execution-tasks.md"
    md_path.write_text(render_markdown_pack(pack), encoding="utf-8")
    json_path = outputs_dir / "campaign-execution-tasks.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")
    notion_path = outputs_dir / "notion-task-payload.json"
    notion_path.write_text(
        json.dumps(to_notion_payload(pack), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Audit.
    prev = memory.last_audit_hash(args.client)
    event = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="build_tasks_cli",
        occurred_at=_utcnow(),
        client_slug=args.client,
        payload={
            "execution_task_pack": {
                "pack_id": pack.pack_id,
                "client_slug": pack.client_slug,
                "total_tasks": pack.total_tasks,
                "blocks_publish": pack.blocks_publish,
                "action": "built",
            }
        },
        prev_hash=prev,
    )
    memory.append_audit_event(event)

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "report_id": pack.report_id,
        "approval_pack_id": pack.approval_pack_id,
        "creative_pack_id": pack.creative_pack_id,
        "visual_pack_id": pack.visual_pack_id,
        "blocks_publish": pack.blocks_publish,
        "total_tasks": pack.total_tasks,
        "count_by_state": pack.count_by_state(),
        "count_by_priority": pack.count_by_priority(),
        "count_by_category": pack.count_by_category(),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "notion_payload_path": str(notion_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_notion_plan(args: argparse.Namespace, *, out) -> int:
    """Build the Notion sync dry-run plan (MKT-5A) from a persisted
    :class:`CampaignExecutionTaskPack` (MKT-4E).

    DRY RUN ONLY. No Notion API call. No credential. No write.

    Exit codes:
    - 0 on success
    - 2 when no task pack exists for ``--client``
    """
    from core.execution import (
        EXECUTION_TASK_PACK_KIND,
        CampaignExecutionTaskPack,
    )
    from core.execution import SINGLETON_ID as TASK_PACK_SINGLETON
    from core.memory import EntityNotFound, JsonFileMemory
    from core.notion_sync import NotionSyncPlanner, render_markdown_plan

    memory = JsonFileMemory(Path(args.root))

    try:
        pack_raw = memory.get(
            args.client, EXECUTION_TASK_PACK_KIND, TASK_PACK_SINGLETON
        )
    except EntityNotFound:
        print(
            f"error: no CampaignExecutionTaskPack for client {args.client!r} "
            f"under {args.root}; run `mkt build-tasks` first.",
            file=out,
        )
        return 2
    pack = CampaignExecutionTaskPack.model_validate(pack_raw)

    planner = NotionSyncPlanner(memory=memory)
    plan = planner.plan(pack)
    planner.persist(plan)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "notion-sync-plan.md"
    md_path.write_text(render_markdown_plan(plan), encoding="utf-8")
    json_path = outputs_dir / "notion-sync-plan.json"
    json_path.write_text(plan.to_json(indent=2), encoding="utf-8")

    payload = {
        "plan_id": plan.plan_id,
        "client_slug": plan.client_slug,
        "task_pack_id": plan.task_pack_id,
        "contract_version": plan.contract_version,
        "blocks_publish": plan.blocks_publish,
        "stats": {
            "total_tasks": plan.stats.total_tasks,
            "would_create": plan.stats.would_create,
            "skip_blocked": plan.stats.skip_blocked,
            "skip_invalid": plan.stats.skip_invalid,
            "issues_total": plan.stats.issues_total,
            "issues_error": plan.stats.issues_error,
            "issues_warning": plan.stats.issues_warning,
            "issues_info": plan.stats.issues_info,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": plan.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_notion_sync(args: argparse.Namespace, *, out) -> int:
    """Execute the Notion sync (MKT-5B). Dry-run by default; only writes
    when ``--write --confirm`` is BOTH set AND the env vars / SDK are
    available AND the plan has no ERROR-severity issues.

    Exit codes:
    - 0 on success (dry-run or real write)
    - 2 when there is no NotionSyncPlan / task pack for the client
    - 3 when ``--write`` is set without ``--confirm`` (safety gate)
    """
    import os

    from core.memory import EntityNotFound, JsonFileMemory
    from core.notion_sync import (
        NoNotionCredentialsError,
        NotionClientWriter,
        NotionSyncExecutor,
        RefusingNotionWriter,
        SyncMode,
        render_markdown_report,
    )

    # ---- Safety gate ----
    write_requested = getattr(args, "write", False)
    confirmed = getattr(args, "confirm", False)
    dry_run = getattr(args, "dry_run", False) or not write_requested

    if write_requested and not confirmed:
        print(
            "error: --write requires --confirm. Refusing to call Notion without "
            "explicit confirmation.",
            file=out,
        )
        return 3

    # ---- Memory + verify upstream artifacts ----
    memory = JsonFileMemory(Path(args.root))
    from core.notion_sync import NOTION_SYNC_PLAN_KIND
    from core.notion_sync import SINGLETON_ID as PLAN_SINGLETON

    try:
        memory.get(args.client, NOTION_SYNC_PLAN_KIND, PLAN_SINGLETON)
    except EntityNotFound:
        print(
            f"error: no NotionSyncPlan for client {args.client!r}; run "
            "`mkt notion-plan` first.",
            file=out,
        )
        return 2

    # ---- Resolve credentials + writer ----
    token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_TASKS_DATABASE_ID") or getattr(
        args, "database_id", None
    )
    token_env_present = bool(token)
    database_id_env_present = bool(os.environ.get("NOTION_TASKS_DATABASE_ID"))

    # Lazy-check the SDK availability without importing it.
    import importlib.util
    sdk_available = importlib.util.find_spec("notion_client") is not None

    writer = RefusingNotionWriter()
    write_blocked_reason: str | None = None
    if dry_run:
        write_blocked_reason = "Modo dry-run (default). No se intentó escribir."
    elif not token:
        write_blocked_reason = (
            "NOTION_TOKEN no está seteado; el sync se ejecuta como dry-run."
        )
        print(
            "WARNING: --write --confirm requested but NOTION_TOKEN is not set. "
            "Falling back to dry-run.",
            file=sys.stderr,
        )
    elif not database_id:
        write_blocked_reason = (
            "NOTION_TASKS_DATABASE_ID no está seteado; el sync se "
            "ejecuta como dry-run."
        )
        print(
            "WARNING: --write --confirm requested but NOTION_TASKS_DATABASE_ID "
            "is not set. Falling back to dry-run.",
            file=sys.stderr,
        )
    else:
        # Token + DB id present. Try to instantiate the real writer.
        try:
            writer = NotionClientWriter(token=token, database_id=database_id)
        except NoNotionCredentialsError as e:
            write_blocked_reason = f"{e}"
            print(
                f"WARNING: cannot construct NotionClientWriter: {e}. Falling "
                "back to dry-run.",
                file=sys.stderr,
            )

    # ---- Run executor ----
    executor = NotionSyncExecutor(
        memory=memory, writer=writer, database_id=database_id
    )
    mode = SyncMode.WRITE if write_requested else SyncMode.DRY_RUN
    report = executor.run(
        args.client,
        mode=mode,
        confirmed=confirmed,
        token_env_present=token_env_present,
        database_id_env_present=database_id_env_present,
        sdk_available=sdk_available,
        write_blocked_reason=write_blocked_reason,
    )
    executor.persist_report(report)

    # ---- Write outputs ----
    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "notion-sync-report.md"
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    json_path = outputs_dir / "notion-sync-report.json"
    json_path.write_text(report.to_json(indent=2), encoding="utf-8")

    payload = {
        "report_id": report.report_id,
        "client_slug": report.client_slug,
        "plan_id": report.plan_id,
        "task_pack_id": report.task_pack_id,
        "mode": report.mode.value,
        "confirmed": report.confirmed,
        "write_attempted": report.write_attempted,
        "write_blocked_reason": report.write_blocked_reason,
        "stats": {
            "total_records": report.stats.total_records,
            "created": report.stats.created,
            "skipped_blocked": report.stats.skipped_blocked,
            "skipped_invalid": report.stats.skipped_invalid,
            "skipped_already_synced": report.stats.skipped_already_synced,
            "skipped_refused": report.stats.skipped_refused,
            "failed": report.stats.failed,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_n8n_plan(args: argparse.Namespace, *, out) -> int:
    """Build the n8n execution dry-run payload (MKT-5C).

    DRY RUN ONLY. No HTTP call, no webhook URL read, no message sent.

    Exit codes:
    - 0 on success
    - 2 when no CampaignRunSummary is found for the client (every
      other upstream artifact is optional).
    """
    from core.memory import EntityNotFound, JsonFileMemory
    from core.n8n_sync import (
        N8nPayloadPlanner,
        render_markdown_payload,
    )
    from core.pipeline import PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON

    memory = JsonFileMemory(Path(args.root))

    try:
        memory.get(args.client, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON)
    except EntityNotFound:
        print(
            f"error: no CampaignRunSummary for client {args.client!r}; run "
            "`mkt run-campaign` first.",
            file=out,
        )
        return 2

    planner = N8nPayloadPlanner(memory=memory)
    payload = planner.plan(args.client)
    planner.persist(payload)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "n8n-execution-plan.md"
    md_path.write_text(render_markdown_payload(payload), encoding="utf-8")
    json_path = outputs_dir / "n8n-execution-payload.json"
    json_path.write_text(payload.to_json(indent=2), encoding="utf-8")

    summary = {
        "payload_id": payload.payload_id,
        "client_slug": payload.client_slug,
        "contract_version": payload.contract_version,
        "blocks_publish": payload.blocks_publish,
        "stats": {
            "total_actions": payload.stats.total_actions,
            "planned": payload.stats.planned,
            "blocked": payload.stats.blocked,
            "by_type": payload.stats.by_type,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": payload.rule_set_id,
    }
    print(json.dumps(summary, indent=2, default=str), file=out)
    return 0


def _cmd_import_metrics(args: argparse.Namespace, *, out) -> int:
    """Import a CSV/JSON file of metrics (MKT-6A).

    Source must be one of: ga4, search_console, social, email, manual.

    Exit codes:
    - 0 on success (even with rejected rows; check the report)
    - 2 when the file is missing / unparseable
    """
    from core.analytics import (
        AnalyticsImporter,
        ImporterError,
        MetricSource,
        render_markdown_import_report,
    )
    from core.memory import JsonFileMemory

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"error: file not found: {file_path}", file=out)
        return 2

    try:
        source = MetricSource(args.source)
    except ValueError:
        print(
            f"error: invalid source {args.source!r}; expected one of "
            f"{', '.join(s.value for s in MetricSource)}.",
            file=out,
        )
        return 2

    memory = JsonFileMemory(Path(args.root))
    importer = AnalyticsImporter(memory=memory)
    try:
        report, snapshot = importer.import_file(
            client_slug=args.client, source=source, file_path=file_path
        )
    except ImporterError as e:
        print(f"error: {e}", file=out)
        return 2

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "analytics-import-report.md"
    md_path.write_text(render_markdown_import_report(report), encoding="utf-8")
    json_path = outputs_dir / "analytics-import-report.json"
    json_path.write_text(report.to_json(indent=2), encoding="utf-8")

    payload = {
        "import_id": report.import_id,
        "client_slug": report.client_slug,
        "source": report.source.value,
        "file_path": report.file_path,
        "rows_imported": report.rows_imported,
        "rows_rejected": report.rows_rejected,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_total_rows": snapshot.total_rows,
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_analyze_metrics(args: argparse.Namespace, *, out) -> int:
    """Analyze the persisted MetricsSnapshot and emit a recommendation pack.

    Exit codes:
    - 0 on success
    - 2 when there is no MetricsSnapshot for the client (run
      `mkt import-metrics` at least once first)
    """
    from core.analytics import (
        AnalyticsAnalyzer,
        render_markdown_recommendations,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    analyzer = AnalyticsAnalyzer(memory=memory)
    try:
        pack = analyzer.analyze(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    analyzer.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "analytics-recommendations.md"
    md_path.write_text(render_markdown_recommendations(pack), encoding="utf-8")
    json_path = outputs_dir / "analytics-recommendations.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "snapshot_id": pack.snapshot_id,
        "total_rows_analyzed": pack.total_rows_analyzed,
        "best_channel": pack.best_channel,
        "worst_channel": pack.worst_channel,
        "channels": [c.channel for c in pack.channels],
        "seo_opportunities": len(pack.seo_opportunities.opportunities),
        "recommendations": len(pack.recommendations),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_feedback_plan(args: argparse.Namespace, *, out) -> int:
    """Build the campaign feedback pack (MKT-6B) from analytics
    recommendations + the rest of the persisted campaign artifacts.

    Exit codes:
    - 0 on success
    - 2 when there is no OptimizationRecommendationPack for the client
      (run `mkt analyze-metrics` first)
    """
    from core.feedback import (
        FeedbackPlanner,
        render_markdown_feedback,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    planner = FeedbackPlanner(memory=memory)
    try:
        pack = planner.plan(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    planner.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "campaign-feedback-pack.md"
    md_path.write_text(render_markdown_feedback(pack), encoding="utf-8")
    json_path = outputs_dir / "campaign-feedback-pack.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "recommendation_pack_id": pack.recommendation_pack_id,
        "snapshot_id": pack.snapshot_id,
        "stats": {
            "total_items": pack.total_items,
            "high_priority_tasks": pack.stats.high_priority_tasks,
            "total_suggested_tasks": pack.stats.total_suggested_tasks,
            "channel_adjustments": pack.stats.channel_adjustments,
            "content_suggestions": pack.stats.content_suggestions,
            "seo_recommendations": pack.stats.seo_recommendations,
            "email_recommendations": pack.stats.email_recommendations,
            "social_recommendations": pack.stats.social_recommendations,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_apply_feedback(args: argparse.Namespace, *, out) -> int:
    """Build the next-campaign iteration plan (MKT-6C) from the
    persisted CampaignFeedbackPack + the rest of the campaign
    artifacts.

    DOES NOT apply changes to any existing pack. Suggestions only.

    Exit codes:
    - 0 on success
    - 2 when there is no CampaignFeedbackPack for the client
      (run `mkt feedback-plan` first)
    """
    from core.iteration import (
        IterationPlanner,
        render_markdown_iteration_plan,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    planner = IterationPlanner(memory=memory)
    try:
        plan = planner.plan(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    planner.persist(plan)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "next-campaign-iteration-plan.md"
    md_path.write_text(render_markdown_iteration_plan(plan), encoding="utf-8")
    json_path = outputs_dir / "next-campaign-iteration-plan.json"
    json_path.write_text(plan.to_json(indent=2), encoding="utf-8")

    payload = {
        "plan_id": plan.plan_id,
        "client_slug": plan.client_slug,
        "contract_version": plan.contract_version,
        "feedback_pack_id": plan.feedback_pack_id,
        "stats": {
            "total_items": plan.total_items,
            "total_actions": plan.stats.total_actions,
            "repeats": plan.stats.repeats,
            "pauses": plan.stats.pauses,
            "improves": plan.stats.improves,
            "creates": plan.stats.creates,
            "channel_adjustments": plan.stats.channel_adjustments,
            "new_content_ideas": plan.stats.new_content_ideas,
            "ab_test_hypotheses": plan.stats.ab_test_hypotheses,
            "calendar_entries": plan.stats.calendar_entries,
            "suggested_tasks": plan.stats.suggested_tasks,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": plan.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_analytics_fetch(args: argparse.Namespace, *, out) -> int:
    """Run a read-only analytics fetch (MKT-6D).

    Pulls data from GA4 or Search Console via the official Google
    SDK in read-only mode (``run_report`` / ``searchanalytics.query``
    only), normalises the rows into :class:`MetricRow` and appends
    them to the per-client :class:`MetricsSnapshot`.

    Behaviour without credentials / SDK / ``--dry-run``: the
    service emits a ``FetchStatus.SKIPPED`` report with a clear
    reason, writes the report MD/JSON, registers an audit
    ``fetch_skipped`` event and exits 0 (degraded, not an error).

    Exit codes:
    - 0 on success (including SKIPPED / FAILED — both are recorded,
      not crashes).
    - 2 when ``--source`` is missing / unsupported (argparse) or the
      service raises a configuration ValueError.
    """

    from core.analytics.connectors import (
        DEFAULT_LOOKBACK_DAYS,
        AnalyticsFetchService,
        resolve_connector,
    )
    from core.analytics.connectors.service import write_report_outputs
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    try:
        connector = resolve_connector(args.source, dry_run=args.dry_run)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2

    service = AnalyticsFetchService(
        memory=memory,
        connector=connector,
        lookback_days=args.lookback_days or DEFAULT_LOOKBACK_DAYS,
    )
    report = service.run(client_slug=args.client)

    outputs_dir = Path(args.outputs_dir)
    md_path, json_path = write_report_outputs(report, outputs_dir=outputs_dir)

    payload = {
        "report_id": report.report_id,
        "client_slug": report.client_slug,
        "contract_version": report.contract_version,
        "source": report.source,
        "status": report.status.value,
        "rows_fetched": report.rows_fetched,
        "rows_normalized": report.rows_normalized,
        "rows_rejected": report.rows_rejected,
        "snapshot_id": report.snapshot_id,
        "sdk_available": report.sdk_available,
        "credentials_available": report.credentials_available,
        "dry_run": report.dry_run,
        "lookback_days": report.lookback_days,
        "identifier_fingerprint": report.identifier_fingerprint,
        "reason": report.reason,
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_ads_analyze(args: argparse.Namespace, *, out) -> int:
    """Run the Google Ads analyzer (MKT-6F) over the persisted
    metrics snapshot.

    Reads ``MetricsSnapshot`` rows tagged with
    ``MetricSource.GOOGLE_ADS``, applies a deterministic rule set
    and emits a :class:`GoogleAdsInsightPack`.

    Exit codes:
    - 0 on success.
    - 2 when there is no ``MetricsSnapshot`` for the client.
    """

    from core.ads_analysis import (
        GoogleAdsAnalyzer,
        render_markdown_ads_insights,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    analyzer = GoogleAdsAnalyzer(memory=memory)
    try:
        pack = analyzer.analyze(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    analyzer.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "google-ads-insight-pack.md"
    md_path.write_text(render_markdown_ads_insights(pack), encoding="utf-8")
    json_path = outputs_dir / "google-ads-insight-pack.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "snapshot_id": pack.snapshot_id,
        "stats": {
            "total_insights": pack.stats.total_insights,
            "ad_groups_profiled": pack.stats.ad_groups_profiled,
            "rows_analyzed": pack.stats.rows_analyzed,
            "by_severity": pack.stats.by_severity,
            "by_action": pack.stats.by_action,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_intake(args: argparse.Namespace, *, out) -> int:
    """Read a client intake JSON, validate it, and produce a StrategyInputBrief.

    Disk side effects:
    - persists the validated intake and validation result to memory.
    - writes ``outputs/<slug>/intake.json``, ``outputs/<slug>/intake-summary.md``
      and ``outputs/<slug>/brief.json`` (the latter is ready to feed
      ``mkt run-strategy --brief``).

    Exit codes:
    - 0 on success (including with warnings).
    - 2 when the input file is missing, unreadable or fails Pydantic validation.
    - 4 when ``--strict`` is set and the validator returned critical issues.
    """
    from core.intake import (
        INTAKE_KIND,
        SINGLETON_ID,
        VALIDATION_KIND,
        ClientIntake,
        IntakeNormalizationError,
        IntakeValidator,
        normalize_intake,
        render_intake_summary,
    )
    from core.memory import JsonFileMemory

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"error: intake file not found: {file_path}", file=out)
        return 2
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        intake = ClientIntake.model_validate(raw)
    except Exception as e:  # noqa: BLE001 — surface schema errors as exit 2
        print(f"error: invalid intake: {e}", file=out)
        return 2

    validation = IntakeValidator().validate(intake)
    slug = validation.client_slug

    memory = JsonFileMemory(Path(args.root))
    memory.put(slug, INTAKE_KIND, SINGLETON_ID, intake.model_dump(mode="json"))
    memory.put(slug, VALIDATION_KIND, SINGLETON_ID, validation.model_dump(mode="json"))

    # Audit event.
    from core.contracts import AuditEventType, AuditTrailEvent
    from core.domain.base import utcnow as _utcnow

    prev = memory.last_audit_hash(slug)
    event = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="intake_cli",
        occurred_at=_utcnow(),
        client_slug=slug,
        payload={
            "intake": {
                "intake_id": validation.intake_id,
                "client_slug": slug,
                "is_valid": validation.is_valid,
                "missing_critical": validation.missing_critical_count,
                "missing_warning": validation.missing_warning_count,
                "missing_info": validation.missing_info_count,
                "action": "created",
            }
        },
        prev_hash=prev,
    )
    memory.append_audit_event(event)

    # Outputs (per-client subdirectory so multiple intakes coexist).
    outputs_dir = Path(args.outputs_dir) / slug
    outputs_dir.mkdir(parents=True, exist_ok=True)
    intake_path = outputs_dir / "intake.json"
    intake_path.write_text(intake.to_json(indent=2), encoding="utf-8")
    md_path = outputs_dir / "intake-summary.md"
    md_path.write_text(render_intake_summary(intake, validation), encoding="utf-8")

    brief_path: Path | None = None
    if validation.can_normalize:
        try:
            brief = normalize_intake(intake, validation)
        except IntakeNormalizationError as e:
            print(f"error: normalization failed: {e}", file=out)
            return 2
        brief_path = outputs_dir / "brief.json"
        brief_path.write_text(brief.to_json(indent=2), encoding="utf-8")

    if (
        getattr(args, "strict", False)
        and validation.missing_critical_count > 0
    ):
        print(
            "error: --strict and critical issues present "
            f"({validation.missing_critical_count})",
            file=out,
        )
        # Still write the summary + intake so the reviewer can fix.
        return 4

    payload = {
        "intake_id": validation.intake_id,
        "client_slug": slug,
        "is_valid": validation.is_valid,
        "can_normalize": validation.can_normalize,
        "missing_critical": validation.missing_critical_count,
        "missing_warning": validation.missing_warning_count,
        "missing_info": validation.missing_info_count,
        "operational_defaults_applied": validation.operational_defaults_applied,
        "intake_path": str(intake_path),
        "summary_path": str(md_path),
        "brief_path": str(brief_path) if brief_path else None,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_run_campaign(args: argparse.Namespace, *, out) -> int:
    """Run the full campaign pipeline from an intake JSON.

    Chains intake (MKT-3E) → strategy (MKT-3A) → approval (MKT-3B) →
    creative (MKT-3C) → visual (MKT-3D) → final summary (MKT-3F).

    Exit codes:
    - 0 — pipeline succeeded (with or without warnings).
    - 2 — intake file missing.
    - 3 — ``--require-approval`` set AND the Approval Pack blocks publish.
    - 4 — ``--strict`` set AND the intake has critical issues.
    """
    import os

    from core.memory import JsonFileMemory
    from core.pipeline import (
        PipelineBlockedByApproval,
        PipelineOrchestrator,
        PipelineStrictFailure,
    )
    from core.strategy import (
        AnthropicSDKInvoker,
        ClaudeStrategyBackend,
        NoCredentialsError,
        RefusingClaudeInvoker,
        StrategyBackend,
    )

    intake_path = Path(args.intake)
    if not intake_path.exists():
        print(f"error: intake file not found: {intake_path}", file=out)
        return 2

    # Backend selection. ``templated`` (default) = no injection — orchestrator
    # uses the deterministic path. ``claude`` = wire ClaudeStrategyBackend.
    # The invoker depends on whether ANTHROPIC_API_KEY is present AND whether
    # the optional `anthropic` SDK is installed:
    #   - key + SDK present → AnthropicSDKInvoker (real Claude calls, MKT-4B).
    #   - key missing OR SDK missing → RefusingClaudeInvoker (MKT-4A behavior:
    #     every call falls back to templated, surfaced in audit + summary +
    #     stderr; pipeline still exits 0).
    backend_choice = getattr(args, "backend", "templated")
    strategy_backend: StrategyBackend | None = None
    if backend_choice == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        claude_model = getattr(args, "claude_model", None) or os.environ.get(
            "ANTHROPIC_MODEL"
        )
        if not api_key:
            # Warnings always to sys.stderr so JSON parsers reading stdout
            # never see them (tests and downstream consumers).
            print(
                "WARNING: --backend claude requested but ANTHROPIC_API_KEY is "
                "not set. Wiring RefusingClaudeInvoker — every creative method "
                "will fall back to the templated backend. Set the env var to "
                "enable real Claude calls.",
                file=sys.stderr,
            )
            strategy_backend = ClaudeStrategyBackend(invoker=RefusingClaudeInvoker())
        else:
            try:
                invoker = AnthropicSDKInvoker(
                    api_key=api_key, model=claude_model
                )
                strategy_backend = ClaudeStrategyBackend(invoker=invoker)
            except NoCredentialsError as e:
                # The `anthropic` SDK is not installed. Reason text is safe.
                print(
                    f"WARNING: --backend claude requested but the SDK is not "
                    f"available: {e}. Falling back to templated.",
                    file=sys.stderr,
                )
                strategy_backend = ClaudeStrategyBackend(
                    invoker=RefusingClaudeInvoker()
                )

    memory = JsonFileMemory(Path(args.root))
    orchestrator = PipelineOrchestrator(
        memory=memory, outputs_root=Path(args.outputs_dir)
    )
    try:
        summary = orchestrator.run_from_file(
            intake_path,
            strict=getattr(args, "strict", False),
            require_approval=getattr(args, "require_approval", False),
            stop_on_blocked=getattr(args, "stop_on_blocked", False),
            strategy_backend=strategy_backend,
        )
    except PipelineStrictFailure as e:
        print(f"error: {e}", file=out)
        return 4
    except PipelineBlockedByApproval as e:
        print(f"error: {e}", file=out)
        return 3

    # Loudly surface fallbacks on stderr — the CLI exit is still 0 (the
    # pipeline completed correctly with the templated fallback), but the
    # operator must see that Claude real was NOT used. Stderr is always
    # sys.stderr regardless of the test's ``out`` redirection so JSON
    # parsers on stdout do not see the WARNING line.
    if summary.backend_requested == "claude" and summary.backend_fallback_count > 0:
        print(
            f"WARNING: --backend claude requested but {summary.backend_fallback_count} "
            f"of 6 creative method(s) fell back to templated. "
            f"effective backend = '{summary.backend_effective}'. "
            "No real Claude invoker is wired (MKT-4A ships infrastructure only; "
            "wire one in MKT-4B). See campaign-final-summary.md for details.",
            file=sys.stderr,
        )

    payload = {
        "run_id": summary.run_id,
        "client_slug": summary.client_slug,
        "contract_version": summary.contract_version,
        "overall_state": summary.overall_state.value,
        "blocks_publish": summary.blocks_publish,
        "is_complete": summary.is_complete,
        "duration_seconds": round(summary.duration_seconds, 3),
        "intake_critical": summary.intake_critical_count,
        "intake_warning": summary.intake_warning_count,
        "intake_info": summary.intake_info_count,
        "report_id": summary.report_id,
        "approval_pack_id": summary.approval_pack_id,
        "creative_pack_id": summary.creative_pack_id,
        "visual_pack_id": summary.visual_pack_id,
        "stage_counts": summary.count_by_outcome(),
        "outputs_dir": str(Path(args.outputs_dir) / summary.client_slug),
        "backend_requested": summary.backend_requested,
        "backend_effective": summary.backend_effective,
        "backend_fallback_count": summary.backend_fallback_count,
        "backend_fallback_notes": list(summary.backend_fallback_notes),
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


# -------- parser --------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mkt",
        description="MARKETING-AGENCY-OS CLI (MKT-2A: minimal dispatcher).",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # list-workflows
    p_lw = subs.add_parser("list-workflows", help="list available workflows")
    p_lw.add_argument(
        "--workflows-dir",
        default=str(DEFAULT_WORKFLOWS_DIR),
        help=f"workflows directory (default: {DEFAULT_WORKFLOWS_DIR})",
    )
    p_lw.set_defaults(func=_cmd_list_workflows)

    # validate-specs
    p_vs = subs.add_parser(
        "validate-specs", help="lint workflows, agents and skills"
    )
    p_vs.add_argument(
        "--workflows-dir", default=str(DEFAULT_WORKFLOWS_DIR)
    )
    p_vs.add_argument("--agents-dir", default=str(DEFAULT_AGENTS_DIR))
    p_vs.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR))
    p_vs.set_defaults(func=_cmd_validate_specs)

    # memory inspect
    p_mem = subs.add_parser("memory", help="memory operations")
    mem_subs = p_mem.add_subparsers(dest="memory_command", required=True)
    p_mi = mem_subs.add_parser("inspect", help="inspect local storage state")
    p_mi.add_argument("--client", default=None, help="client slug (optional)")
    p_mi.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_mi.set_defaults(func=_cmd_memory_inspect)

    # run-mock
    p_rm = subs.add_parser(
        "run-mock", help="run a workflow with the MockAgent backend"
    )
    p_rm.add_argument("workflow_id", help="e.g. W1_intake_to_strategy")
    p_rm.add_argument("--client", required=True, help="client slug")
    p_rm.add_argument("--workflows-dir", default=str(DEFAULT_WORKFLOWS_DIR))
    p_rm.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_rm.set_defaults(func=_cmd_run_mock)

    # run-strategy
    p_rs = subs.add_parser(
        "run-strategy",
        help="run the W7 campaign strategy engine on a brief JSON file",
    )
    p_rs.add_argument(
        "--brief",
        required=True,
        help="path to the strategy input brief JSON file",
    )
    p_rs.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_rs.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the Markdown report is written (default: outputs/)",
    )
    p_rs.add_argument(
        "--audit",
        action="store_true",
        help="chain a claim audit + Approval Pack generation after the strategy run",
    )
    p_rs.set_defaults(func=_cmd_run_strategy)

    # audit-strategy
    p_as = subs.add_parser(
        "audit-strategy",
        help="audit a persisted CampaignStrategyReport and produce an Approval Pack",
    )
    p_as.add_argument("--client", required=True, help="client slug")
    p_as.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_as.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the Approval Pack Markdown is written (default: outputs/)",
    )
    p_as.set_defaults(func=_cmd_audit_strategy)

    # build-creatives
    p_bc = subs.add_parser(
        "build-creatives",
        help="build a CreativeAssetPack from the persisted strategy + approval pack",
    )
    p_bc.add_argument("--client", required=True, help="client slug")
    p_bc.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_bc.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the Markdown + JSON outputs are written (default: outputs/)",
    )
    p_bc.add_argument(
        "--require-approval",
        action="store_true",
        help="fail with exit 3 when the Approval Pack blocks publish",
    )
    p_bc.set_defaults(func=_cmd_build_creatives)

    # build-visuals
    p_bv = subs.add_parser(
        "build-visuals",
        help="build a Visual Direction Pack (prompts + specs per piece type)",
    )
    p_bv.add_argument("--client", required=True, help="client slug")
    p_bv.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_bv.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the Markdown + JSON outputs are written (default: outputs/)",
    )
    p_bv.add_argument(
        "--require-approval",
        action="store_true",
        help="fail with exit 3 when the Approval Pack blocks publish",
    )
    p_bv.set_defaults(func=_cmd_build_visuals)

    # build-tasks (MKT-4E)
    p_bt = subs.add_parser(
        "build-tasks",
        help=(
            "build a CampaignExecutionTaskPack from the persisted strategy + "
            "approval + creative + visual packs. Notion-ready; does NOT call Notion."
        ),
    )
    p_bt.add_argument("--client", required=True, help="client slug")
    p_bt.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_bt.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory for the Markdown + JSON + Notion-payload files (default: outputs/)",
    )
    p_bt.set_defaults(func=_cmd_build_tasks)

    # notion-plan (MKT-5A)
    p_np = subs.add_parser(
        "notion-plan",
        help=(
            "build the Notion sync DRY RUN plan from the persisted execution "
            "task pack. Does NOT call Notion, does NOT use credentials."
        ),
    )
    p_np.add_argument("--client", required=True, help="client slug")
    p_np.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_np.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where notion-sync-plan.{md,json} are written (default: outputs/)",
    )
    p_np.set_defaults(func=_cmd_notion_plan)

    # notion-sync (MKT-5B)
    p_ns = subs.add_parser(
        "notion-sync",
        help=(
            "execute the Notion sync. DRY-RUN by default; requires "
            "BOTH --write and --confirm to actually call Notion. Even "
            "then, missing NOTION_TOKEN / NOTION_TASKS_DATABASE_ID falls "
            "back to dry-run with a clear warning."
        ),
    )
    p_ns.add_argument("--client", required=True, help="client slug")
    p_ns.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_ns.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where notion-sync-report.{md,json} are written",
    )
    p_ns.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "explicit dry-run flag (also the default when --write is absent)"
        ),
    )
    p_ns.add_argument(
        "--write",
        action="store_true",
        help=(
            "request real Notion writes. Requires --confirm; without it "
            "the CLI exits with code 3 and writes nothing."
        ),
    )
    p_ns.add_argument(
        "--confirm",
        action="store_true",
        help="explicit confirmation gate for --write",
    )
    p_ns.add_argument(
        "--database-id",
        default=None,
        help=(
            "override NOTION_TASKS_DATABASE_ID. Ignored unless --write "
            "--confirm is also set."
        ),
    )
    p_ns.set_defaults(func=_cmd_notion_sync)

    # n8n-plan (MKT-5C)
    p_n8 = subs.add_parser(
        "n8n-plan",
        help=(
            "build the n8n execution DRY-RUN payload from the persisted "
            "campaign + creative + visual + notion-sync artifacts. Does NOT "
            "call n8n, does NOT read webhook URLs, does NOT send anything."
        ),
    )
    p_n8.add_argument("--client", required=True, help="client slug")
    p_n8.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_n8.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where n8n-execution-{plan.md,payload.json} are written",
    )
    p_n8.set_defaults(func=_cmd_n8n_plan)

    # import-metrics (MKT-6A)
    p_im = subs.add_parser(
        "import-metrics",
        help=(
            "import a CSV/JSON metrics export for one client. "
            "MANUAL ONLY — no API call, no credential read."
        ),
    )
    p_im.add_argument("--client", required=True, help="client slug")
    p_im.add_argument("--file", required=True, help="path to a .csv or .json file")
    p_im.add_argument(
        "--source",
        required=True,
        choices=("ga4", "search_console", "social", "email", "manual"),
        help="data source the file was exported from",
    )
    p_im.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_im.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the import report MD/JSON are written",
    )
    p_im.set_defaults(func=_cmd_import_metrics)

    # analyze-metrics (MKT-6A)
    p_am = subs.add_parser(
        "analyze-metrics",
        help=(
            "analyze the persisted metrics snapshot and emit a "
            "deterministic OptimizationRecommendationPack. "
            "No external API, no LLM."
        ),
    )
    p_am.add_argument("--client", required=True, help="client slug")
    p_am.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_am.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the recommendation MD/JSON are written",
    )
    p_am.set_defaults(func=_cmd_analyze_metrics)

    # feedback-plan (MKT-6B)
    p_fp = subs.add_parser(
        "feedback-plan",
        help=(
            "build the CampaignFeedbackPack from the persisted analytics "
            "recommendation pack + the rest of the campaign artifacts. "
            "Deterministic, LLM-free, no external API. Suggestions only."
        ),
    )
    p_fp.add_argument("--client", required=True, help="client slug")
    p_fp.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_fp.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the feedback pack MD/JSON are written",
    )
    p_fp.set_defaults(func=_cmd_feedback_plan)

    # apply-feedback (MKT-6C)
    p_af = subs.add_parser(
        "apply-feedback",
        help=(
            "build the NextCampaignIterationPlan from the persisted "
            "CampaignFeedbackPack. Deterministic, LLM-free, no external "
            "API. The plan never applies changes — suggestions only."
        ),
    )
    p_af.add_argument("--client", required=True, help="client slug")
    p_af.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_af.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the iteration plan MD/JSON are written",
    )
    p_af.set_defaults(func=_cmd_apply_feedback)

    # analytics-fetch (MKT-6D)
    p_xfetch = subs.add_parser(
        "analytics-fetch",
        help=(
            "fetch metrics from a read-only Google connector (GA4 or "
            "Search Console). No mutation, no Google Ads, no MCP. "
            "Skips gracefully without credentials."
        ),
    )
    p_xfetch.add_argument("--client", required=True, help="client slug")
    p_xfetch.add_argument(
        "--source",
        required=True,
        choices=("ga4", "search_console", "google_ads"),
        help="connector source (read-only)",
    )
    p_xfetch.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "force the connector to skip the upstream call regardless "
            "of credential / SDK availability"
        ),
    )
    p_xfetch.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="lookback window in days (default: 28)",
    )
    p_xfetch.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_xfetch.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the fetch report MD/JSON are written",
    )
    p_xfetch.set_defaults(func=_cmd_analytics_fetch)

    # ads-analyze (MKT-6F)
    p_ads = subs.add_parser(
        "ads-analyze",
        help=(
            "run native Google Ads rules over the persisted metrics "
            "snapshot. Read-only — no campaign mutation, no budget "
            "change, suggestions only."
        ),
    )
    p_ads.add_argument("--client", required=True, help="client slug")
    p_ads.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_ads.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the insight pack MD/JSON are written",
    )
    p_ads.set_defaults(func=_cmd_ads_analyze)

    # intake
    p_in = subs.add_parser(
        "intake",
        help="validate and normalize a client intake JSON into a StrategyInputBrief",
    )
    p_in.add_argument("--file", required=True, help="path to the intake JSON file")
    p_in.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_in.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where intake.json + intake-summary.md + brief.json are written (default: outputs/)",
    )
    p_in.add_argument(
        "--strict",
        action="store_true",
        help="fail with exit 4 when the validator returns critical issues",
    )
    p_in.set_defaults(func=_cmd_intake)

    # run-campaign
    p_rc = subs.add_parser(
        "run-campaign",
        help="run the full campaign pipeline (intake → strategy → approval → creative → visual) in one command",
    )
    p_rc.add_argument("--intake", required=True, help="path to the intake JSON file")
    p_rc.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_rc.add_argument(
        "--outputs-dir",
        default="outputs",
        help="root directory where per-client outputs are written (default: outputs/)",
    )
    p_rc.add_argument(
        "--strict",
        action="store_true",
        help="fail with exit 4 when the intake has critical issues",
    )
    p_rc.add_argument(
        "--require-approval",
        action="store_true",
        help="fail with exit 3 when the Approval Pack blocks publish",
    )
    p_rc.add_argument(
        "--stop-on-blocked",
        action="store_true",
        help="halt cleanly (exit 0) after approval when the pack blocks publish — skips creative + visual stages",
    )
    p_rc.add_argument(
        "--backend",
        choices=("templated", "claude"),
        default="templated",
        help=(
            "strategy content backend. 'templated' (default) = deterministic, "
            "LLM-free. 'claude' = LLM-backed via Anthropic SDK, with automatic "
            "fallback to templated on any error. Requires ANTHROPIC_API_KEY "
            "and the optional `anthropic` package (`pip install -e .[claude]`)."
        ),
    )
    p_rc.add_argument(
        "--claude-model",
        default=None,
        help=(
            "override the Claude model used by --backend claude. "
            "Falls back to ANTHROPIC_MODEL env var, then to the package "
            "default (claude-sonnet-4-5-...)."
        ),
    )
    p_rc.set_defaults(func=_cmd_run_campaign)

    return parser


def main(argv: Sequence[str] | None = None, *, out=None) -> int:
    """Entry point. ``argv`` is ``sys.argv[1:]`` if not provided."""
    out = out or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args, out=out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
