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
    from core.approval import get_latest_for_client
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

    # MKT-11E compatibility shim: the most recent approval for this
    # client, resolved dynamically (no more singleton read).
    approval_pack = get_latest_for_client(memory, args.client)

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
    from core.approval import get_latest_for_client
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

    # MKT-11E compatibility shim: most recent approval, resolved dynamically.
    approval_pack = get_latest_for_client(memory, args.client)

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

    from core.approval import get_latest_for_client
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

    # MKT-11E compatibility shim: most recent approval, resolved dynamically.
    approval = get_latest_for_client(memory, args.client)

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

    # MKT-6H opt-in: promote AdsFeedbackBridgePack tasks into the
    # execution pack. Without the flag, behaviour is unchanged.
    if getattr(args, "include_ads_bridge", False):
        bridge = _load_ads_bridge_pack_or_none(memory, args.client)
        if bridge is not None:
            from core.ads_promoter import promote_into_execution_tasks
            result = promote_into_execution_tasks(bridge, pack)
            _audit_ads_promotion(
                memory, client_slug=args.client,
                target="campaign_execution_task_pack",
                bridge_pack_id=bridge.pack_id,
                promotion_result=result,
            )

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
    import datetime as _datetime_mod

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

    # Parse optional period arguments.
    period_start: _datetime_mod.date | None = None
    period_end: _datetime_mod.date | None = None
    if getattr(args, "period_start", None):
        try:
            period_start = _datetime_mod.date.fromisoformat(args.period_start)
        except ValueError:
            print(f"error: invalid --period-start {args.period_start!r}; expected YYYY-MM-DD", file=out)
            return 2
    if getattr(args, "period_end", None):
        try:
            period_end = _datetime_mod.date.fromisoformat(args.period_end)
        except ValueError:
            print(f"error: invalid --period-end {args.period_end!r}; expected YYYY-MM-DD", file=out)
            return 2

    memory = JsonFileMemory(Path(args.root))
    importer = AnalyticsImporter(memory=memory)
    try:
        report, snapshot = importer.import_file(
            client_slug=args.client,
            source=source,
            file_path=file_path,
            period_start=period_start,
            period_end=period_end,
            period_label=getattr(args, "period_label", None) or None,
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
        "period_start": str(report.period_start) if report.period_start else None,
        "period_end": str(report.period_end) if report.period_end else None,
        "period_label": report.period_label,
        "period_snapshot_entity_id": report.period_snapshot_entity_id,
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


def _load_ads_bridge_pack_or_none(memory, client_slug: str):
    """Load the persisted ``AdsFeedbackBridgePack`` for ``client_slug``
    or return ``None`` when it does not exist. Used by the three
    ``--include-ads-bridge`` opt-in promotion flows (MKT-6H)."""

    from core.ads_feedback.models import (
        ADS_FEEDBACK_BRIDGE_PACK_KIND,
        AdsFeedbackBridgePack,
    )
    from core.ads_feedback.models import (
        SINGLETON_ID as ADS_BRIDGE_SINGLETON,
    )
    from core.memory import EntityNotFound

    try:
        raw = memory.get(
            client_slug, ADS_FEEDBACK_BRIDGE_PACK_KIND, ADS_BRIDGE_SINGLETON,
        )
    except EntityNotFound:
        return None
    return AdsFeedbackBridgePack.model_validate(raw)


def _audit_ads_promotion(
    memory, *, client_slug: str, target: str, bridge_pack_id: str,
    promotion_result,
) -> None:
    """Append one audit event documenting a ``--include-ads-bridge``
    promotion run (MKT-6H)."""

    from core.contracts import AuditEventType, AuditTrailEvent
    from core.domain.base import utcnow as _utcnow

    prev = memory.last_audit_hash(client_slug)
    event = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE,
        actor="ads_bridge_promoter",
        occurred_at=_utcnow(),
        client_slug=client_slug,
        payload={
            "ads_bridge_promotion": {
                "action": "promoted",
                "target": target,
                "bridge_pack_id": bridge_pack_id,
                "recommendations_promoted": (
                    promotion_result.recommendations_promoted
                ),
                "tasks_promoted": promotion_result.tasks_promoted,
                "channel_adjustments_promoted": (
                    promotion_result.channel_adjustments_promoted
                ),
                "content_suggestions_promoted": (
                    promotion_result.content_suggestions_promoted
                ),
                "iteration_actions_promoted": (
                    promotion_result.iteration_actions_promoted
                ),
                "duplicates_skipped": promotion_result.duplicates_skipped,
            }
        },
        prev_hash=prev,
    )
    memory.append_audit_event(event)


def _cmd_feedback_plan(args: argparse.Namespace, *, out) -> int:
    """Build the campaign feedback pack (MKT-6B) from analytics
    recommendations + the rest of the persisted campaign artifacts.

    With ``--include-ads-bridge`` (MKT-6H), the persisted
    :class:`AdsFeedbackBridgePack` is opt-in folded in: ads
    recommendations become extra :class:`SuggestedTask` /
    :class:`ContentSuggestion` entries, ads campaign adjustments
    become extra ``google_ads`` :class:`ChannelAdjustment` entries.
    Without the flag, behaviour is byte-compatible with pre-MKT-6H.

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

    promotion = None
    if getattr(args, "include_ads_bridge", False):
        bridge = _load_ads_bridge_pack_or_none(memory, args.client)
        if bridge is not None:
            from core.ads_promoter import promote_into_feedback_pack
            promotion = promote_into_feedback_pack(bridge, pack)
            _audit_ads_promotion(
                memory, client_slug=args.client,
                target="campaign_feedback_pack",
                bridge_pack_id=bridge.pack_id,
                promotion_result=promotion,
            )

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

    # MKT-6H opt-in: promote ads bridge campaign adjustments +
    # suggested tasks into the iteration plan. Without the flag,
    # behaviour is byte-compatible with pre-MKT-6H.
    if getattr(args, "include_ads_bridge", False):
        bridge = _load_ads_bridge_pack_or_none(memory, args.client)
        if bridge is not None:
            from core.ads_promoter import promote_into_iteration_plan
            result = promote_into_iteration_plan(bridge, plan)
            _audit_ads_promotion(
                memory, client_slug=args.client,
                target="next_campaign_iteration_plan",
                bridge_pack_id=bridge.pack_id,
                promotion_result=result,
            )

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


def _cmd_seo_report(args: argparse.Namespace, *, out) -> int:
    """Build the SEO Intelligence Report Pack (MKT-10C).

    Deterministic consolidation of ClientIntake + MetricsSnapshot (GA4 /
    Search Console) + an optional operator-supplied evidence file
    (``--input``) into an auditable SEO diagnosis + roadmap report.

    No scraping. No external API. No LLM. No site mutation.

    Exit codes:
    - 0 on success (even with zero evidence — missing categories are
      recorded explicitly, never fabricated).
    - 2 when ``--input`` is given but the file is missing / unparseable,
      or when ``--period-start``/``--period-end`` are malformed.

    MKT-11A: this command is a thin adapter over
    :func:`core.application.services.seo.build_seo_report`. Behaviour is
    unchanged — see ``docs/MKT-11A-Application-Services-Inventory.md``.
    """
    from core.application import ErrorCode, OperationContext
    from core.application.services.seo import build_seo_report

    outputs_dir = Path(args.output_dir)
    md_path = outputs_dir / "seo-intelligence-report.md"
    json_path = outputs_dir / "seo-intelligence-report.json"

    ctx = OperationContext(
        client_slug=args.client, root=Path(args.root), outputs_root=outputs_dir,
    )
    result = build_seo_report(
        ctx,
        start_date=getattr(args, "start_date", None),
        end_date=getattr(args, "end_date", None),
        period_label=getattr(args, "period_label", None) or None,
        input_path=getattr(args, "input", None),
        overwrite=getattr(args, "overwrite", False),
        dry_run=getattr(args, "dry_run", False),
    )

    if not result.ok:
        assert result.error is not None
        if result.error.code is ErrorCode.ALREADY_EXISTS:
            print(
                f"error: output already exists at {outputs_dir} — pass --overwrite to replace it",
                file=out,
            )
        else:
            print(f"error: {result.error.message}", file=out)
        return 2

    pack = result.data
    if getattr(args, "dry_run", False):
        payload = {
            "dry_run": True,
            "report_id": pack.report_id,
            "client_slug": pack.client_slug,
            "would_write": [str(a.path) for a in result.artifacts],
            "facts_count": pack.executive_summary.facts_count,
            "hypotheses_count": pack.executive_summary.hypotheses_count,
            "missing_evidence_count": len(pack.missing_evidence),
        }
        print(json.dumps(payload, indent=2, default=str), file=out)
        return 0

    payload = {
        "report_id": pack.report_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "period_start": str(pack.period_start) if pack.period_start else None,
        "period_end": str(pack.period_end) if pack.period_end else None,
        "period_label": pack.period_label,
        "facts_count": pack.executive_summary.facts_count,
        "hypotheses_count": pack.executive_summary.hypotheses_count,
        "recommendations_count": pack.executive_summary.recommendations_count,
        "missing_evidence_count": len(pack.missing_evidence),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_approvals_list(args: argparse.Namespace, *, out) -> int:
    """List ApprovalPacks — pending review / blocking publish by default,
    or narrowed with ``--client`` / ``--status`` / ``--limit`` (MKT-11A +
    MKT-11B, D-11.5).

    Cross-tenant by design when ``--client`` is omitted — an Approval
    Queue has no meaning scoped to a single client. Read-only.

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success (an empty queue is not an error).
    - 2 when ``--status`` is not a recognised state.
    """
    from core.application import ErrorCode, exit_code_for
    from core.application.services import approvals

    status = getattr(args, "status", None)
    parsed_status = None
    if status:
        from core.approval import ApprovalState

        try:
            parsed_status = ApprovalState(status)
        except ValueError:
            print(
                f"error: invalid --status {status!r}; expected one of "
                f"{', '.join(s.value for s in ApprovalState)}",
                file=out,
            )
            return exit_code_for(ErrorCode.INVALID_INPUT)

    result = approvals.list_pending(
        root=Path(args.root),
        client_slug=getattr(args, "client", None) or None,
        status=parsed_status,
        job_id=getattr(args, "job_id", None) or None,
        limit=getattr(args, "limit", None),
    )
    payload = {
        "count": len(result.data),
        "pending": [
            {
                "client_slug": row.client_slug,
                "approval_id": row.approval_id,
                "pack_id": row.pack_id,
                "state": row.state.value,
                "overall_severity": row.overall_severity,
                "blocks_publish": row.blocks_publish,
                "job_id": row.job_id,
            }
            for row in result.data
        ],
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_approvals_show(args: argparse.Namespace, *, out) -> int:
    """Show one approval for a client (MKT-11A/11B/11E).

    ``--approval-id`` selects a specific approval by its real, versioned
    identity. When omitted, resolves the client's pending approvals: one
    → shown; zero or more than one → a structured error (never guessed).

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success.
    - 2 when ``--approval-id`` is omitted and more than one approval is
      pending for the client (ambiguous).
    - 3 when the approval does not exist for the client.
    - 6 when the persisted record exists but cannot be read back (corrupted
      JSON or a schema mismatch).
    """
    from core.application import OperationContext, exit_code_for
    from core.application.services import approvals

    ctx = OperationContext(client_slug=args.client, root=Path(args.root))
    result = approvals.show(ctx, approval_id=getattr(args, "approval_id", None) or None)
    if not result.ok:
        assert result.error is not None
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)

    pack = result.data
    print(pack.to_json(indent=2), file=out)
    return 0


def _cmd_approve(args: argparse.Namespace, *, out) -> int:
    """Approve one specific approval for one client (MKT-11A/11B/11E).

    Wraps :meth:`core.approval.ApprovalPackBuilder.approve` — idempotent
    when the pack is already APPROVED (exit 0, warning surfaced).
    ``--approval-id`` selects the real, versioned approval to act on; when
    omitted, resolves the client's pending approvals (one → used; zero or
    more than one → structured error, never guessed). Requires a role
    authorized to decide (``operator`` / ``approver`` / ``admin`` — see
    ``core.application.policies``); the CLI's ``OperationContext`` uses
    its default role, so this only matters for callers that build their
    own context (a future API/worker).

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success (including the idempotent no-op case).
    - 2 when ``--approval-id`` is omitted and more than one approval is
      pending for the client (ambiguous).
    - 3 when the approval does not exist for the client.
    - 4 when the transition is invalid (e.g. the pack is already REJECTED).
    - 5 when the actor's role is not authorized to decide.
    - 6 when the persisted pack exists but cannot be read back.
    """
    from core.application import OperationContext, exit_code_for
    from core.application.services import approvals

    ctx_kwargs: dict = dict(
        client_slug=args.client, root=Path(args.root), actor_id=args.actor,
    )
    correlation_id = getattr(args, "correlation_id", None)
    if correlation_id:
        ctx_kwargs["correlation_id"] = correlation_id
    ctx = OperationContext(**ctx_kwargs)

    result = approvals.approve(
        ctx,
        notes=getattr(args, "notes", None) or None,
        approval_id=getattr(args, "approval_id", None) or None,
    )
    if not result.ok:
        assert result.error is not None
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)

    pack = result.data
    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "state": pack.state.value,
        "blocks_publish": pack.blocks_publish,
        "audit_event_id": result.audit_event_id,
        "correlation_id": ctx.correlation_id,
        "warnings": [w.message for w in result.warnings],
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_reject(args: argparse.Namespace, *, out) -> int:
    """Reject one specific approval for one client (MKT-11A/11B/11E).

    Wraps :meth:`core.approval.ApprovalPackBuilder.reject`. ``--reason``
    is mandatory — enforced at the application layer. Idempotent when the
    pack is already REJECTED (exit 0, warning surfaced). ``--approval-id``
    selects the real, versioned approval; when omitted, resolves the
    client's pending approvals (one → used; zero or more than one →
    structured error, never guessed).

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success (including the idempotent no-op case).
    - 2 when ``--reason`` is empty, or ``--approval-id`` is omitted and
      more than one approval is pending for the client (ambiguous).
    - 3 when the approval does not exist for the client.
    - 4 when the transition is invalid (e.g. the pack is already APPROVED).
    - 5 when the actor's role is not authorized to decide.
    - 6 when the persisted pack exists but cannot be read back.
    """
    from core.application import OperationContext, exit_code_for
    from core.application.services import approvals

    ctx_kwargs: dict = dict(
        client_slug=args.client, root=Path(args.root), actor_id=args.actor,
    )
    correlation_id = getattr(args, "correlation_id", None)
    if correlation_id:
        ctx_kwargs["correlation_id"] = correlation_id
    ctx = OperationContext(**ctx_kwargs)

    result = approvals.reject(
        ctx,
        reason=args.reason,
        approval_id=getattr(args, "approval_id", None) or None,
    )
    if not result.ok:
        assert result.error is not None
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)

    pack = result.data
    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "state": pack.state.value,
        "blocks_publish": pack.blocks_publish,
        "audit_event_id": result.audit_event_id,
        "correlation_id": ctx.correlation_id,
        "warnings": [w.message for w in result.warnings],
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_jobs_submit(args: argparse.Namespace, *, out) -> int:
    """Submit a new QUEUED job for one client (MKT-11C).

    Does not execute the job — pass ``--run`` to submit and execute in
    the same call, or run it later with ``mkt jobs run``.

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success.
    - 2 when ``--params`` is not valid JSON, or fails the operation's
      params contract, or the operation is unregistered.
    - 5 when the actor's role is not authorized to execute jobs.
    """
    from core.application import OperationContext, exit_code_for
    from core.application.services import jobs

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        print(f"error: invalid --params JSON: {e}", file=out)
        return 2

    ctx_kwargs: dict = dict(
        client_slug=args.client, root=Path(args.root), actor_id=args.actor,
        outputs_root=Path(getattr(args, "outputs_dir", None) or "outputs"),
    )
    correlation_id = getattr(args, "correlation_id", None)
    if correlation_id:
        ctx_kwargs["correlation_id"] = correlation_id
    ctx = OperationContext(**ctx_kwargs)

    result = jobs.submit_job(ctx, operation=args.operation, params=params)
    if not result.ok:
        assert result.error is not None
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)

    record = result.data
    if getattr(args, "run", False):
        run_result = jobs.run_job(ctx, job_id=record.job_id)
        return _handle_run_result(run_result, out=out)

    print(json.dumps(_job_payload(record), indent=2, default=str), file=out)
    return 0


def _cmd_jobs_run(args: argparse.Namespace, *, out) -> int:
    """Execute a QUEUED job (MKT-11C). Idempotent on COMPLETED.

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success (including the idempotent no-op case).
    - 3 when the job does not exist.
    - 4 when the job is not in a runnable state (only QUEUED can run).
    - 5 when the actor's role is not authorized to execute jobs.
    - 6 when the persisted job exists but cannot be read back.
    - 7 when the job runs and reaches FAILED.
    """
    from core.application import OperationContext
    from core.application.services import jobs

    ctx = OperationContext(
        client_slug=args.client, root=Path(args.root), actor_id=args.actor,
        outputs_root=Path(getattr(args, "outputs_dir", None) or "outputs"),
    )
    result = jobs.run_job(ctx, job_id=args.job_id)
    return _handle_run_result(result, out=out)


def _handle_run_result(result, *, out) -> int:
    """Shared exit-code logic for both ``jobs run`` and ``jobs submit
    --run`` — a FAILED job gets its own exit code (7), distinct from the
    generic error mapping, because the job system worked correctly and
    only the operation failed."""
    from core.application import exit_code_for
    from core.application.exit_codes import ExitCode
    from core.jobs import JobState

    if not result.ok:
        assert result.error is not None
        if result.data is not None and getattr(result.data, "state", None) is JobState.FAILED:
            # A FAILED job is a normal, structured outcome — the JSON
            # payload already carries `error`, so stdout stays clean JSON
            # (no extra "error: " line); the diagnostic goes to stderr.
            print(f"job failed: {result.error.message}", file=sys.stderr)
            print(json.dumps(_job_payload(result.data), indent=2, default=str), file=out)
            return int(ExitCode.JOB_FAILED)
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)

    return _print_job_result(result, out=out)


def _cmd_jobs_list(args: argparse.Namespace, *, out) -> int:
    """List jobs for one client, newest first (MKT-11C). Read-only.

    Exit codes:
    - 0 always (an empty list is not an error).
    """
    from core.application import OperationContext
    from core.application.services import jobs

    ctx = OperationContext(client_slug=args.client, root=Path(args.root))
    result = jobs.list_jobs(
        ctx,
        state=getattr(args, "status", None) or None,
        operation=getattr(args, "operation", None) or None,
        limit=getattr(args, "limit", None),
    )
    payload = {
        "count": len(result.data),
        "jobs": [_job_payload(v.job, liveness=v.liveness) for v in result.data],
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_jobs_show(args: argparse.Namespace, *, out) -> int:
    """Show one job by id (MKT-11C). Read-only.

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success.
    - 3 when the job does not exist.
    - 6 when the persisted job exists but cannot be read back.
    """
    from core.application import OperationContext, exit_code_for
    from core.application.services import jobs

    ctx = OperationContext(client_slug=args.client, root=Path(args.root))
    result = jobs.show_job(ctx, job_id=args.job_id)
    if not result.ok:
        assert result.error is not None
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)
    print(
        json.dumps(
            _job_payload(result.data.job, liveness=result.data.liveness),
            indent=2, default=str,
        ),
        file=out,
    )
    return 0


def _cmd_jobs_cancel(args: argparse.Namespace, *, out) -> int:
    """Cancel a QUEUED or WAITING_APPROVAL job (MKT-11C). Idempotent on
    CANCELLED. A RUNNING job cannot be cancelled by the inline runner —
    see ``core.jobs.InlineJobRunner.cancel``.

    Exit codes (see ``core.application.exit_codes.ExitCode``):
    - 0 on success (including the idempotent no-op case).
    - 3 when the job does not exist.
    - 4 when the job cannot be cancelled from its current state.
    - 5 when the actor's role is not authorized.
    - 6 when the persisted job exists but cannot be read back.
    """
    from core.application import OperationContext, exit_code_for
    from core.application.services import jobs

    ctx = OperationContext(
        client_slug=args.client, root=Path(args.root), actor_id=args.actor,
    )
    result = jobs.cancel_job(ctx, job_id=args.job_id)
    if not result.ok:
        assert result.error is not None
        print(f"error: {result.error.message}", file=out)
        return exit_code_for(result.error.code)
    return _print_job_result(result, out=out)


def _job_payload(record, *, liveness=None) -> dict:
    payload = {
        "job_id": record.job_id,
        "client_slug": record.client_slug,
        "operation": record.operation,
        "state": record.state.value,
        "correlation_id": record.correlation_id,
        "attempt": record.attempt,
        "created_at": str(record.created_at),
        "started_at": str(record.started_at) if record.started_at else None,
        "finished_at": str(record.finished_at) if record.finished_at else None,
        "result_data": record.result_data,
        "result_ref": record.result_ref,
        "error": (
            {"code": record.error.code.value, "message": record.error.message}
            if record.error else None
        ),
        "approval_reason": record.approval_reason,
    }
    # job-execution-robustness: only show/list resolve a liveness
    # observation (submit/run/cancel don't — the record they return is
    # already known-fresh at that instant, a probe would be redundant).
    if liveness is not None:
        payload["liveness"] = liveness.value
    return payload


def _print_job_result(result, *, out) -> int:
    """Shared success-path printer for run/cancel — surfaces warnings on
    stderr, the job record as clean JSON on stdout."""
    for w in result.warnings:
        print(f"WARNING: {w.message}", file=sys.stderr)
    payload = _job_payload(result.data)
    payload["warnings"] = [w.message for w in result.warnings]
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_ads_feedback(args: argparse.Namespace, *, out) -> int:
    """Bridge the Google Ads insight pack into the feedback loop
    (MKT-6G).

    Reads a persisted ``GoogleAdsInsightPack``, turns each insight
    into recommendations, campaign adjustments, keyword proposals
    and suggested tasks, and persists an ``AdsFeedbackBridgePack``.

    Exit codes:
    - 0 on success.
    - 2 when there is no ``GoogleAdsInsightPack`` for the client.
    """

    from core.ads_feedback import (
        AdsFeedbackBridge,
        render_markdown_ads_bridge,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    bridge = AdsFeedbackBridge(memory=memory)
    try:
        pack = bridge.build(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    bridge.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "ads-feedback-bridge-pack.md"
    md_path.write_text(render_markdown_ads_bridge(pack), encoding="utf-8")
    json_path = outputs_dir / "ads-feedback-bridge-pack.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "insight_pack_id": pack.insight_pack_id,
        "feedback_pack_id": pack.feedback_pack_id,
        "execution_task_pack_id": pack.execution_task_pack_id,
        "iteration_plan_id": pack.iteration_plan_id,
        "stats": {
            "total_recommendations": pack.stats.total_recommendations,
            "total_campaign_adjustments": pack.stats.total_campaign_adjustments,
            "total_keyword_proposals": pack.stats.total_keyword_proposals,
            "total_suggested_tasks": pack.stats.total_suggested_tasks,
            "by_recommendation_kind": pack.stats.by_recommendation_kind,
            "by_recommendation_priority": pack.stats.by_recommendation_priority,
            "by_adjustment_kind": pack.stats.by_adjustment_kind,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_image_jobs(args: argparse.Namespace, *, out) -> int:
    """Build an ImageGenerationJobPack (MKT-7A) from the persisted
    VisualDirectionPack + optional ApprovalPack / CreativeAssetPack /
    CampaignRunSummary.

    NO image is generated. NO provider is called. The block emits a
    structured pack of jobs the operator reviews before any real
    integration ships.

    Exit codes:
    - 0 on success
    - 2 when there is no VisualDirectionPack for the client
    """
    from core.image_jobs import (
        ImageJobFactory,
        render_markdown_image_jobs,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    factory = ImageJobFactory(memory=memory)
    try:
        pack = factory.build(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    factory.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "image-generation-jobs.md"
    md_path.write_text(render_markdown_image_jobs(pack), encoding="utf-8")
    json_path = outputs_dir / "image-generation-jobs.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "visual_pack_id": pack.visual_pack_id,
        "creative_pack_id": pack.creative_pack_id,
        "approval_pack_id": pack.approval_pack_id,
        "blocks_publish": pack.blocks_publish,
        "stats": {
            "total_jobs": pack.stats.total_jobs,
            "directions_consumed": pack.stats.directions_consumed,
            "blocked_due_to_approval": pack.stats.blocked_due_to_approval,
            "blocked_due_to_direction": pack.stats.blocked_due_to_direction,
            "by_state": pack.stats.by_state,
            "by_provider_suggestion": pack.stats.by_provider_suggestion,
            "by_piece_type": pack.stats.by_piece_type,
        },
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": pack.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


_PORTAL_INSTALL_HINT = (
    "Streamlit is not installed. Install the optional `portal` extra:\n"
    "    pip install -e \".[portal]\""
)


def _cmd_portal(args: argparse.Namespace, *, out) -> int:
    """Launch the read-only Streamlit portal (MKT-9A).

    Thin wrapper over ``streamlit run portal/app.py``. The wrapper
    does NOT write any file — it only spawns the Streamlit server
    after verifying the dependency is available.

    Exit codes:
    - 0 when the portal exits cleanly.
    - 2 when Streamlit is not installed (with install hint).
    """

    # Probe streamlit without importing the heavy modules. We use
    # importlib.util.find_spec so the wrapper itself does not need
    # streamlit at import time.
    import importlib.util

    if importlib.util.find_spec("streamlit") is None:
        print(_PORTAL_INSTALL_HINT, file=out)
        return 2

    import subprocess

    repo_root = Path(__file__).resolve().parents[1]
    app_path = repo_root / "portal" / "app.py"
    if not app_path.exists():
        print(f"error: portal app missing at {app_path}", file=out)
        return 2

    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--", "--root", str(args.root), "--outputs-dir", str(args.outputs_dir),
    ]
    # Stream Streamlit's stdout/stderr to the operator terminal —
    # capture nothing, write nothing to disk.
    return subprocess.call(cmd)


def _cmd_atlas_handoff(args: argparse.Namespace, *, out) -> int:
    """Build an ATLAS handoff brief (MKT-8A) for one of three kinds:
    ``landing`` / ``branding`` / ``page_design``.

    The handoff is a plain Markdown + JSON deliverable. No HTTP
    call. No reach-in into ATLAS — the operator copies / pastes
    the brief into whatever ATLAS workflow they use today.

    Exit codes:
    - 0 on success
    - 2 when there is no CampaignStrategyReport for the client
      (run `mkt run-strategy` / `mkt run-campaign` first)
    """
    from core.atlas_bridge import (
        AtlasHandoffFactory,
        AtlasHandoffKind,
        render_markdown_atlas_handoff,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    factory = AtlasHandoffFactory(memory=memory)
    try:
        kind = AtlasHandoffKind(args.kind)
    except ValueError:
        print(
            f"error: unsupported kind {args.kind!r} — must be one of "
            "landing | branding | page_design",
            file=out,
        )
        return 2
    try:
        handoff = factory.build(
            client_slug=args.client, kind=kind, page_name=args.page_name,
        )
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    factory.persist(handoff)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    # Per MKT-8A final spec: ``atlas-<kind>-brief.{md,json}``.
    # ``page_design`` stays hyphenated for filesystem-friendliness.
    file_kind = kind.value.replace("_", "-")
    md_path = outputs_dir / f"atlas-{file_kind}-brief.md"
    md_path.write_text(render_markdown_atlas_handoff(handoff), encoding="utf-8")
    json_path = outputs_dir / f"atlas-{file_kind}-brief.json"
    json_path.write_text(handoff.to_json(indent=2), encoding="utf-8")

    payload = {
        "handoff_id": handoff.handoff_id,
        "client_slug": handoff.client_slug,
        "contract_version": handoff.contract_version,
        "kind": handoff.kind.value,
        "strategy_report_id": handoff.strategy_report_id,
        "creative_pack_id": handoff.creative_pack_id,
        "visual_pack_id": handoff.visual_pack_id,
        "approval_pack_id": handoff.approval_pack_id,
        "image_job_pack_id": handoff.image_job_pack_id,
        "blocks_publish": handoff.blocks_publish,
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "rule_set_id": handoff.rule_set_id,
    }
    print(json.dumps(payload, indent=2, default=str), file=out)
    return 0


def _cmd_image_provider_plan(args: argparse.Namespace, *, out) -> int:
    """Score image providers + emit a dry-run preview per job (MKT-7B).

    Reads the persisted ImageGenerationJobPack (MKT-7A), evaluates
    every candidate provider against weighted criteria, picks one
    per job (fallback `manual`) and writes a per-job dry-run
    receipt — the simulated request *shape* a future integration
    block would send.

    NO HTTP. NO SDK import. NO credential read. NO image generation.

    Exit codes:
    - 0 on success
    - 2 when there is no ImageGenerationJobPack for the client
    """
    from core.image_provider_plan import (
        ImageProviderPlanner,
        render_markdown_provider_plan,
    )
    from core.memory import JsonFileMemory

    memory = JsonFileMemory(Path(args.root))
    planner = ImageProviderPlanner(memory=memory)
    try:
        pack = planner.plan(args.client)
    except ValueError as e:
        print(f"error: {e}", file=out)
        return 2
    planner.persist(pack)

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    md_path = outputs_dir / "image-provider-plan.md"
    md_path.write_text(render_markdown_provider_plan(pack), encoding="utf-8")
    json_path = outputs_dir / "image-provider-plan.json"
    json_path.write_text(pack.to_json(indent=2), encoding="utf-8")

    payload = {
        "pack_id": pack.pack_id,
        "client_slug": pack.client_slug,
        "contract_version": pack.contract_version,
        "job_pack_id": pack.job_pack_id,
        "blocks_publish": pack.blocks_publish,
        "stats": {
            "total_jobs": pack.stats.total_jobs,
            "by_recommended_provider": pack.stats.by_recommended_provider,
            "by_dry_run_status": pack.stats.by_dry_run_status,
            "overrode_job_suggestion": pack.stats.overrode_job_suggestion,
            "skipped_blocked": pack.stats.skipped_blocked,
            "skipped_manual": pack.stats.skipped_manual,
            "total_estimated_cost_usd": pack.stats.total_estimated_cost_usd,
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


def _cmd_utm_plan(args: argparse.Namespace, *, out) -> int:
    """Generate a UTM tracking plan for a client.

    Reads the existing ``campaign_strategy_report`` from memory and produces
    UTM-tagged links for every channel/piece combination.

    Output files:
    - ``<outputs-dir>/<client>/utm-plan.md``
    - ``<outputs-dir>/<client>/utm-plan.json``

    Exit codes:
    - 0 on success (including when no strategy report exists — a fallback
      plan is generated with a recommendation to run the strategy first).
    - 2 on argument or configuration error.
    """
    from core.intelligence.utm_builder import UTMBuilder, persist_utm_plan
    from core.memory import JsonFileMemory

    client_slug = args.client
    memory = JsonFileMemory(Path(args.root))
    outputs_root = Path(args.outputs_dir)
    base_url = getattr(args, "base_url", None) or "https://example.com"
    period = getattr(args, "period", None) or None

    builder = UTMBuilder(memory, base_url=base_url)
    plan = builder.build(client_slug, period=period)

    md_path, json_path = persist_utm_plan(plan, memory, outputs_root=outputs_root)

    payload = {
        "status": "ok",
        "client_slug": plan.client_slug,
        "campaign_name": plan.campaign_name,
        "period": plan.period,
        "total_links": plan.total_links,
        "channels_covered": plan.channels_covered,
        "utm_plan_md": str(md_path),
        "utm_plan_json": str(json_path),
        "recommendations": len(plan.recommendations),
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

    MKT-11D: backend selection is now
    :func:`core.application.services.campaign_run.resolve_strategy_backend`
    — moved, not reimplemented, so this command and the ``campaign.run``
    job operation share exactly one copy of that logic. Everything else
    (the file-exists preflight, the orchestrator call, the exception
    handling for ``PipelineStrictFailure`` / ``PipelineBlockedByApproval``)
    deliberately stays inline here rather than routing through the shared
    ``run_campaign()`` service function: that function also performs
    MKT-11D's execution-time intake re-validation (Adjustment 2), which
    treats a malformed-but-existing intake file as a hard failure —
    correct for a job that must never trust submit-time state, but a
    behaviour change from this command's long-standing graceful
    degradation (a malformed intake becomes a FAILED *stage* with exit 0,
    not a command failure). Preserving that exact legacy distinction is
    why this command keeps its own control flow.
    """
    from core.application.services.campaign_run import resolve_strategy_backend
    from core.memory import JsonFileMemory
    from core.pipeline import (
        PipelineBlockedByApproval,
        PipelineOrchestrator,
        PipelineStrictFailure,
    )

    intake_path = Path(args.intake)
    if not intake_path.exists():
        print(f"error: intake file not found: {intake_path}", file=out)
        return 2

    strategy_backend, backend_warning = resolve_strategy_backend(
        getattr(args, "backend", "templated"), getattr(args, "claude_model", None),
    )
    if backend_warning:
        # Always sys.stderr so JSON parsers reading stdout never see it
        # (tests and downstream consumers) — same contract as before.
        print(f"WARNING: {backend_warning}", file=sys.stderr)

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
    p_bt.add_argument(
        "--include-ads-bridge",
        action="store_true",
        default=False,
        help=(
            "MKT-6H opt-in: fold the persisted AdsFeedbackBridgePack "
            "recommendations into this task pack. Idempotent — re-runs "
            "skip duplicates."
        ),
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
    p_im.add_argument(
        "--period-start",
        default=None,
        metavar="YYYY-MM-DD",
        help="start of the reporting period (enables time-ranged snapshot)",
    )
    p_im.add_argument(
        "--period-end",
        default=None,
        metavar="YYYY-MM-DD",
        help="end of the reporting period (required when --period-start is set)",
    )
    p_im.add_argument(
        "--period-label",
        default=None,
        help="human-readable period label, e.g. '2024-W24' or '2024-Q2'",
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
    p_fp.add_argument(
        "--include-ads-bridge",
        action="store_true",
        default=False,
        help=(
            "MKT-6H opt-in: fold the persisted AdsFeedbackBridgePack "
            "recommendations + adjustments into this feedback pack. "
            "Idempotent — re-runs skip duplicates."
        ),
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
    p_af.add_argument(
        "--include-ads-bridge",
        action="store_true",
        default=False,
        help=(
            "MKT-6H opt-in: fold the persisted AdsFeedbackBridgePack "
            "campaign adjustments + tasks into this iteration plan. "
            "Idempotent — re-runs skip duplicates."
        ),
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
    p_xfetch.add_argument(
        "--period-label",
        default=None,
        help="human-readable period label for the auto-derived period snapshot",
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

    # ads-feedback (MKT-6G)
    p_adsfb = subs.add_parser(
        "ads-feedback",
        help=(
            "bridge the persisted GoogleAdsInsightPack into the feedback "
            "loop. Read-only — no campaign / keyword / budget mutation, "
            "suggestions only."
        ),
    )
    p_adsfb.add_argument("--client", required=True, help="client slug")
    p_adsfb.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_adsfb.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the bridge pack MD/JSON are written",
    )
    p_adsfb.set_defaults(func=_cmd_ads_feedback)

    # seo-report (MKT-10C)
    p_seo = subs.add_parser(
        "seo-report",
        help=(
            "build the SEO Intelligence Report Pack — deterministic "
            "consolidation of ClientIntake + GA4/Search Console metrics + "
            "operator-supplied evidence. No scraping, no external API, "
            "no LLM, no site mutation."
        ),
    )
    p_seo.add_argument("--client", required=True, help="client slug")
    p_seo.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_seo.add_argument(
        "--start-date",
        default=None,
        dest="start_date",
        metavar="YYYY-MM-DD",
        help="start of the reporting period (enables period-scoped persistence)",
    )
    p_seo.add_argument(
        "--end-date",
        default=None,
        dest="end_date",
        metavar="YYYY-MM-DD",
        help="end of the reporting period (required when --start-date is set)",
    )
    p_seo.add_argument(
        "--period-label",
        default=None,
        help="human-readable period label, e.g. '2024-W24' or '2024-Q2'",
    )
    p_seo.add_argument(
        "--input",
        default=None,
        help="path to a SEOEvidenceInput JSON file (keyword research, "
        "competitors, URL structure, locales, technical notes)",
    )
    p_seo.add_argument(
        "--output-dir",
        default="outputs",
        dest="output_dir",
        help="directory where the report MD/JSON are written",
    )
    p_seo.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite an existing report at --output-dir",
    )
    p_seo.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="build the report without persisting or writing output files",
    )
    p_seo.set_defaults(func=_cmd_seo_report)

    # approvals (MKT-11A, D-11.5)
    p_appr = subs.add_parser("approvals", help="approval queue operations")
    appr_subs = p_appr.add_subparsers(dest="approvals_command", required=True)

    p_appr_list = appr_subs.add_parser(
        "list",
        help="list ApprovalPacks pending review or blocking publish, across all clients",
    )
    p_appr_list.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_appr_list.add_argument(
        "--client", default=None, help="narrow to one client slug (default: all tenants)",
    )
    p_appr_list.add_argument(
        "--status",
        default=None,
        help=(
            "narrow to one ApprovalState (draft|needs_review|approved|rejected). "
            "When given, replaces the default pending/blocked filter."
        ),
    )
    p_appr_list.add_argument(
        "--job-id", dest="job_id", default=None, help="narrow to the approval associated with one job",
    )
    p_appr_list.add_argument(
        "--limit", type=int, default=None, help="cap the number of rows returned",
    )
    p_appr_list.set_defaults(func=_cmd_approvals_list)

    p_appr_show = appr_subs.add_parser(
        "show", help="show one approval for a client",
    )
    p_appr_show.add_argument("--client", required=True, help="client slug")
    p_appr_show.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_appr_show.add_argument(
        "--approval-id",
        dest="approval_id",
        default=None,
        help=(
            "the approval to show (real, versioned identity). If omitted, "
            "resolves the client's sole pending approval when unambiguous."
        ),
    )
    p_appr_show.set_defaults(func=_cmd_approvals_show)

    # approve (MKT-11A, D-11.5)
    p_approve = subs.add_parser(
        "approve", help="approve the current ApprovalPack for one client",
    )
    p_approve.add_argument("--client", required=True, help="client slug")
    p_approve.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_approve.add_argument(
        "--actor",
        default="unknown",
        help="reviewer identity recorded on the approval decision",
    )
    p_approve.add_argument(
        "--notes", default=None, help="optional reviewer notes",
    )
    p_approve.add_argument(
        "--approval-id",
        dest="approval_id",
        default=None,
        help="the approval to act on (real, versioned identity). If omitted, resolves the client's sole pending approval when unambiguous.",
    )
    p_approve.add_argument(
        "--correlation-id",
        dest="correlation_id",
        default=None,
        help="caller-supplied correlation id (default: auto-generated)",
    )
    p_approve.set_defaults(func=_cmd_approve)

    # reject (MKT-11A, D-11.5)
    p_reject = subs.add_parser(
        "reject", help="reject the current ApprovalPack for one client",
    )
    p_reject.add_argument("--client", required=True, help="client slug")
    p_reject.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_reject.add_argument(
        "--actor",
        default="unknown",
        help="reviewer identity recorded on the rejection decision",
    )
    p_reject.add_argument(
        "--reason", required=True, help="mandatory reason for rejection",
    )
    p_reject.add_argument(
        "--approval-id",
        dest="approval_id",
        default=None,
        help="the approval to act on (real, versioned identity). If omitted, resolves the client's sole pending approval when unambiguous.",
    )
    p_reject.add_argument(
        "--correlation-id",
        dest="correlation_id",
        default=None,
        help="caller-supplied correlation id (default: auto-generated)",
    )
    p_reject.set_defaults(func=_cmd_reject)

    # jobs (MKT-11C)
    p_jobs = subs.add_parser("jobs", help="job execution operations")
    jobs_subs = p_jobs.add_subparsers(dest="jobs_command", required=True)

    p_jobs_submit = jobs_subs.add_parser(
        "submit",
        help=(
            "submit a new QUEUED job. demo.echo / demo.fail / "
            "demo.needs_approval are dev/test-only. campaign.run (MKT-11D) "
            "is the first production operation — runs the full campaign "
            "pipeline, equivalent to `mkt run-campaign`."
        ),
    )
    p_jobs_submit.add_argument("--client", required=True, help="client slug")
    p_jobs_submit.add_argument(
        "--operation", required=True, help="registered operation id, e.g. demo.echo",
    )
    p_jobs_submit.add_argument(
        "--params", default=None, help="JSON object of operation params",
    )
    p_jobs_submit.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_jobs_submit.add_argument(
        "--outputs-dir",
        dest="outputs_dir",
        default="outputs",
        help="root directory where per-client outputs are written (default: outputs/) — relevant for operations that produce artifacts (e.g. campaign.run)",
    )
    p_jobs_submit.add_argument(
        "--actor", default="unknown", help="actor identity recorded on the job",
    )
    p_jobs_submit.add_argument(
        "--correlation-id",
        dest="correlation_id",
        default=None,
        help="caller-supplied correlation id (default: auto-generated)",
    )
    p_jobs_submit.add_argument(
        "--run",
        action="store_true",
        help="execute the job immediately after submitting it",
    )
    p_jobs_submit.set_defaults(func=_cmd_jobs_submit)

    p_jobs_run = jobs_subs.add_parser(
        "run", help="execute a QUEUED job (idempotent on COMPLETED)",
    )
    p_jobs_run.add_argument("--client", required=True, help="client slug")
    p_jobs_run.add_argument("--job-id", dest="job_id", required=True, help="job id")
    p_jobs_run.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_jobs_run.add_argument(
        "--outputs-dir",
        dest="outputs_dir",
        default="outputs",
        help="root directory where per-client outputs are written (default: outputs/) — relevant for operations that produce artifacts (e.g. campaign.run)",
    )
    p_jobs_run.add_argument(
        "--actor", default="unknown", help="actor identity recorded on the run",
    )
    p_jobs_run.set_defaults(func=_cmd_jobs_run)

    p_jobs_list = jobs_subs.add_parser(
        "list", help="list jobs for one client, newest first",
    )
    p_jobs_list.add_argument("--client", required=True, help="client slug")
    p_jobs_list.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_jobs_list.add_argument(
        "--status", default=None, help="narrow to one JobState value",
    )
    p_jobs_list.add_argument(
        "--operation", default=None, help="narrow to one operation id",
    )
    p_jobs_list.add_argument(
        "--limit", type=int, default=None, help="cap the number of rows returned",
    )
    p_jobs_list.set_defaults(func=_cmd_jobs_list)

    p_jobs_show = jobs_subs.add_parser("show", help="show one job by id")
    p_jobs_show.add_argument("--client", required=True, help="client slug")
    p_jobs_show.add_argument("--job-id", dest="job_id", required=True, help="job id")
    p_jobs_show.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_jobs_show.set_defaults(func=_cmd_jobs_show)

    p_jobs_cancel = jobs_subs.add_parser(
        "cancel",
        help=(
            "cancel a QUEUED or WAITING_APPROVAL job. A RUNNING job cannot "
            "be cancelled by the inline runner."
        ),
    )
    p_jobs_cancel.add_argument("--client", required=True, help="client slug")
    p_jobs_cancel.add_argument("--job-id", dest="job_id", required=True, help="job id")
    p_jobs_cancel.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_jobs_cancel.add_argument(
        "--actor", default="unknown", help="actor identity recorded on the cancellation",
    )
    p_jobs_cancel.set_defaults(func=_cmd_jobs_cancel)

    # image-jobs (MKT-7A)
    p_imgj = subs.add_parser(
        "image-jobs",
        help=(
            "build an ImageGenerationJobPack from the persisted "
            "VisualDirectionPack. No image is generated; no provider "
            "is called — jobs are review-only deliverables."
        ),
    )
    p_imgj.add_argument("--client", required=True, help="client slug")
    p_imgj.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_imgj.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the image jobs MD/JSON are written",
    )
    p_imgj.set_defaults(func=_cmd_image_jobs)

    # image-provider-plan (MKT-7B)
    p_ipp = subs.add_parser(
        "image-provider-plan",
        help=(
            "score providers + emit dry-run receipts per job. NO "
            "provider is called, NO image is generated, NO credential "
            "is read."
        ),
    )
    p_ipp.add_argument("--client", required=True, help="client slug")
    p_ipp.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_ipp.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the provider plan MD/JSON are written",
    )
    p_ipp.set_defaults(func=_cmd_image_provider_plan)

    # atlas-brief (MKT-8A)
    p_ah = subs.add_parser(
        "atlas-brief",
        help=(
            "build an ATLAS handoff brief (landing / branding / "
            "page_design). No HTTP, no reach-in into ATLAS; the "
            "operator copies the artifact into the ATLAS workflow."
        ),
    )
    p_ah.add_argument("--client", required=True, help="client slug")
    p_ah.add_argument(
        "--kind",
        required=True,
        choices=("landing", "branding", "page_design"),
        help="which handoff brief to build",
    )
    p_ah.add_argument(
        "--page-name",
        default=None,
        help="page name (only used when --kind=page_design)",
    )
    p_ah.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_ah.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where the handoff MD/JSON are written",
    )
    p_ah.set_defaults(func=_cmd_atlas_handoff)

    # portal (MKT-9A)
    p_portal = subs.add_parser(
        "portal",
        help=(
            "launch the read-only Streamlit portal locally. No "
            "writes, no APIs. Requires `pip install -e .[portal]`."
        ),
    )
    p_portal.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_portal.add_argument(
        "--outputs-dir",
        default="outputs",
        help="outputs directory the portal scans (default: outputs)",
    )
    p_portal.set_defaults(func=_cmd_portal)

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
        help="run the full campaign pipeline (intake -> strategy -> approval -> creative -> visual) in one command",
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

    # utm-plan
    p_utm = subs.add_parser(
        "utm-plan",
        help="generate a UTM tracking plan from the client's strategy report",
    )
    p_utm.add_argument("--client", required=True, help="client slug")
    p_utm.add_argument(
        "--root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"memory root (default: {DEFAULT_DATA_ROOT})",
    )
    p_utm.add_argument(
        "--outputs-dir",
        default="outputs",
        help="directory where utm-plan.md and utm-plan.json are written (default: outputs/)",
    )
    p_utm.add_argument(
        "--base-url",
        default="https://example.com",
        dest="base_url",
        help="base landing page URL for UTM link generation (default: https://example.com)",
    )
    p_utm.add_argument(
        "--period",
        default=None,
        help="campaign period label, e.g. 2024-Q3 (default: current YYYY-MM)",
    )
    p_utm.set_defaults(func=_cmd_utm_plan)

    return parser


def main(argv: Sequence[str] | None = None, *, out=None) -> int:
    """Entry point. ``argv`` is ``sys.argv[1:]`` if not provided."""
    out = out or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args, out=out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
