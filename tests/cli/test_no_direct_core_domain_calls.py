"""Architecture guard (architecture/application-service-boundary, Phase 10).

AST-based, not a runtime/import check: parses `cli/main.py` and asserts
that each MIGRATED command function's body contains no `import`/
`from ... import ...` statement reaching into a `core.*` domain package
directly — only `core.application.*` (the service/context/result layer)
is allowed. This is deliberately lightweight (no external tool, no
plugin) and targeted: it does not forbid direct-core imports everywhere
in the file (dozens of NOT-yet-migrated commands still need them — see
the CLI Responsibility Inventory), only inside the specific functions
this milestone moved onto the application-service boundary.

Extend `_MIGRATED_FUNCTIONS` as later batches migrate more commands —
that is the whole point of this guard: a function added here can never
regress back to direct-core imports without this test catching it.
"""

from __future__ import annotations

import ast
from pathlib import Path

CLI_MAIN = Path(__file__).resolve().parents[2] / "cli" / "main.py"

# Function name -> the core.application submodule(s) it's allowed to
# import from `core.application.services.*` (informational only, not
# enforced beyond "core.application.*" generally being allowed below).
_MIGRATED_FUNCTIONS = {
    # batch 1
    "_cmd_build_creatives",
    "_cmd_build_visuals",
    "_cmd_build_tasks",
    "_cmd_intake",
    # batch 2
    "_cmd_import_metrics",
    "_cmd_analyze_metrics",
    "_cmd_analytics_fetch",
    # batch 3
    "_cmd_ads_analyze",
    "_cmd_ads_feedback",
}

# A migrated function may still import these — they are adapter-only
# concerns (argument parsing, path handling, JSON I/O), never domain
# orchestration.
_ALLOWED_NON_APPLICATION_MODULES = {
    "json",
    "pathlib",
    "argparse",
    "sys",
}


def _root_module(dotted: str) -> str:
    return dotted.split(".")[0]


def _is_allowed(module: str | None) -> bool:
    if module is None:
        return True  # a bare `import x` handled separately by caller
    if module.startswith("core.application"):
        return True
    if module == "core.application":
        return True
    if _root_module(module) in _ALLOWED_NON_APPLICATION_MODULES:
        return True
    return not module.startswith("core.")


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in {CLI_MAIN}")


def _violations_in_function(func: ast.FunctionDef) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not _is_allowed(module):
                violations.append(f"from {module} import ... (line {node.lineno})")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("core.") and not _is_allowed(alias.name):
                    violations.append(f"import {alias.name} (line {node.lineno})")
    return violations


def test_migrated_commands_do_not_import_core_domain_directly() -> None:
    tree = ast.parse(CLI_MAIN.read_text(encoding="utf-8"), filename=str(CLI_MAIN))
    all_violations: dict[str, list[str]] = {}
    for name in _MIGRATED_FUNCTIONS:
        func = _find_function(tree, name)
        violations = _violations_in_function(func)
        if violations:
            all_violations[name] = violations

    assert not all_violations, (
        "migrated CLI command(s) regressed to direct core-domain imports "
        f"(only core.application.* is allowed inside them): {all_violations}"
    )


def test_migrated_functions_still_exist() -> None:
    """Guards the guard: if a migrated function gets renamed/removed
    without updating `_MIGRATED_FUNCTIONS`, fail loudly instead of the
    AST walk silently checking nothing."""
    tree = ast.parse(CLI_MAIN.read_text(encoding="utf-8"), filename=str(CLI_MAIN))
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    missing = _MIGRATED_FUNCTIONS - defined
    assert not missing, f"migrated function(s) no longer exist in cli/main.py: {missing}"
