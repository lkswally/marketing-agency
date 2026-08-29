"""SEO Intelligence Report application service (MKT-11A).

Migrates ``mkt seo-report`` (MKT-10C) onto the application layer.
**Behaviour-identical** to the CLI's inline implementation — same build
order, same overwrite/dry-run semantics, same filenames, same payload
shape. See ``docs/MKT-11A-Application-Services-Inventory.md`` §3 (F-1):
this command uses the FLAT output layout, unchanged.
"""

from __future__ import annotations

import datetime as _datetime_mod
import json
from pathlib import Path

from pydantic import ValidationError

from core.memory import JsonFileMemory
from core.seo_intelligence import (
    SEOEvidenceInput,
    SEOIntelligenceReportBuilder,
    render_markdown_seo_report,
)

from ..artifacts import OutputLayout, check_path_allowed, resolve_output_dir, write_artifacts
from ..context import OperationContext
from ..result import ErrorCode, OperationResult

_MD_FILENAME = "seo-intelligence-report.md"
_JSON_FILENAME = "seo-intelligence-report.json"


def build_seo_report(
    ctx: OperationContext,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    period_label: str | None = None,
    input_path: str | Path | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> OperationResult:
    """Build (and, unless dry-run, persist + write) the SEO report."""

    evidence_input: SEOEvidenceInput | None = None
    if input_path:
        resolved_input = Path(input_path)
        if not resolved_input.exists():
            return OperationResult.error_result(
                code=ErrorCode.INVALID_INPUT,
                message=f"file not found: {resolved_input}",
            )
        try:
            raw = json.loads(resolved_input.read_text(encoding="utf-8"))
            evidence_input = SEOEvidenceInput.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as e:
            return OperationResult.error_result(
                code=ErrorCode.INVALID_INPUT,
                message=f"invalid --input file {resolved_input}: {e}",
            )

    period_start, err = _parse_date(start_date, "start_date")
    if err is not None:
        return err
    period_end, err = _parse_date(end_date, "end_date")
    if err is not None:
        return err

    memory = JsonFileMemory(ctx.root)
    builder = SEOIntelligenceReportBuilder(memory=memory)
    pack = builder.build(
        ctx.client_slug,
        period_start=period_start,
        period_end=period_end,
        period_label=period_label or None,
        evidence_input=evidence_input,
    )

    files = {
        _MD_FILENAME: render_markdown_seo_report(pack),
        _JSON_FILENAME: pack.to_json(indent=2),
    }

    if dry_run:
        artifacts, write_err = write_artifacts(
            outputs_root=ctx.outputs_root,
            client_slug=ctx.client_slug,
            layout=OutputLayout.FLAT,
            files=files,
            overwrite=overwrite,
            dry_run=True,
        )
        if write_err is not None:
            return OperationResult.error_result(
                code=write_err.code,
                message=write_err.message,
                remediation=write_err.remediation,
            )
        return OperationResult.ok_result(data=pack, artifacts=artifacts)

    # Mirror the CLI's own pre-flight: check path containment and
    # (unless --overwrite) existence BEFORE persisting anything, so a
    # blocked write never leaves a half-applied side effect.
    out_dir = resolve_output_dir(
        outputs_root=ctx.outputs_root, client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
    )
    candidate_paths = [out_dir / name for name in files]
    for path in candidate_paths:
        if not check_path_allowed(path=path, outputs_root=ctx.outputs_root):
            return OperationResult.error_result(
                code=ErrorCode.PATH_NOT_ALLOWED,
                message=f"resolved artifact path escapes the permitted output root: {path}",
            )
    if not overwrite:
        existing_paths = [p for p in candidate_paths if p.exists()]
        if existing_paths:
            listing = ", ".join(str(p) for p in existing_paths)
            return OperationResult.error_result(
                code=ErrorCode.ALREADY_EXISTS,
                message=f"output already exists: {listing}",
                remediation="pass overwrite=True to replace it",
            )

    builder.persist(pack)

    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
        files=files,
        overwrite=True,  # existence already checked above
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code,
            message=write_err.message,
            remediation=write_err.remediation,
        )
    return OperationResult.ok_result(data=pack, artifacts=artifacts)


def _parse_date(
    value: str | None, field_name: str,
) -> tuple[_datetime_mod.date | None, OperationResult | None]:
    if not value:
        return None, None
    try:
        return _datetime_mod.date.fromisoformat(value), None
    except ValueError:
        return None, OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=f"invalid --{field_name.replace('_', '-')} {value!r}; expected YYYY-MM-DD",
        )


__all__ = ["build_seo_report"]
