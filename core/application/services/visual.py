"""Visual Direction Pack application service (architecture/application-
service-boundary).

Migrates ``mkt build-visuals`` onto the application layer.
Behaviour-identical to the CLI's inline implementation: same build
order, same FLAT output layout, same ``--require-approval`` gate, same
optional (EntityNotFound -> None) CreativeAssetPack resolution.
"""

from __future__ import annotations

from core.approval import get_latest_for_client
from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON_ID
from core.memory import EntityNotFound, JsonFileMemory
from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport
from core.visual import VisualPromptFactory, render_markdown_pack

from ..artifacts import OutputLayout, write_artifacts
from ..context import OperationContext
from ..result import ErrorCode, OperationResult

_MD_FILENAME = "visual-direction-pack.md"
_JSON_FILENAME = "visual-direction-pack.json"


def build_visual_pack(
    ctx: OperationContext, *, require_approval: bool = False,
) -> OperationResult:
    """Build (and persist + write) the Visual Direction Pack for ``ctx.client_slug``."""
    memory = JsonFileMemory(ctx.root)
    try:
        report_raw = memory.get(ctx.client_slug, REPORT_KIND, SINGLETON_ID)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no CampaignStrategyReport for client {ctx.client_slug!r}",
            remediation="run `mkt run-strategy` first",
        )
    report = CampaignStrategyReport.model_validate(report_raw)

    approval_pack = get_latest_for_client(memory, ctx.client_slug)

    creative_pack: CreativeAssetPack | None = None
    try:
        cp_raw = memory.get(ctx.client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON_ID)
        creative_pack = CreativeAssetPack.model_validate(cp_raw)
    except EntityNotFound:
        creative_pack = None

    if require_approval and approval_pack is not None and approval_pack.blocks_publish:
        return OperationResult.error_result(
            code=ErrorCode.POLICY_BLOCKED,
            message="--require-approval set but the Approval Pack blocks publish",
        )

    factory = VisualPromptFactory(memory=memory)
    pack = factory.build(report, approval_pack, creative_pack)
    factory.persist(pack)

    files = {
        _MD_FILENAME: render_markdown_pack(pack),
        _JSON_FILENAME: pack.to_json(indent=2),
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


__all__ = ["build_visual_pack"]
