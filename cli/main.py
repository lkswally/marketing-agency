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

from core.runtime import MinimalDispatcher, MockAgent
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
    dispatcher = MinimalDispatcher(memory=memory, agent=MockAgent())
    summary = dispatcher.run(spec, client_slug=args.client)
    print(json.dumps(summary.model_dump(mode="json"), indent=2, default=str), file=out)
    return 0 if summary.status.value == "succeeded" else 1


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

    return parser


def main(argv: Sequence[str] | None = None, *, out=None) -> int:
    """Entry point. ``argv`` is ``sys.argv[1:]`` if not provided."""
    out = out or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args, out=out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
