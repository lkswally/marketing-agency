"""Declarative registry of the 14 packs the portal surfaces (MKT-9A).

Each :class:`PortalPackSpec` says:

- ``order`` — position in the portal page (1..14).
- ``kind`` — JsonFileMemory ``kind`` discriminator.
- ``singleton_id`` — entity id (almost always ``"current"``).
- ``title`` — human label.
- ``markdown_filenames`` — possible filenames under
  ``outputs/<slug>/`` (the first one that exists wins).
- ``blocks_publish_field`` — if the pack carries a posture flag
  (e.g. ``blocks_publish``), the field name on the JSON dict;
  ``None`` means the pack cannot block publish.
- ``optional`` — when ``True``, MISSING is informational; when
  ``False``, MISSING is a pre-flight blocker.
- ``description`` — short doc text shown in the portal expander
  header.

Nothing in this module imports streamlit. The registry is a pure
declarative table consumed by both the app and the unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortalPackSpec:
    """One entry in the portal's left-to-right pack registry."""

    order: int
    kind: str
    singleton_id: str
    """Primary singleton id the loader probes first."""

    title: str
    markdown_filenames: tuple[str, ...]
    blocks_publish_field: str | None
    optional: bool
    description: str
    extra_singleton_ids: tuple[str, ...] = ()
    """MKT-9B: optional list of additional singleton ids the loader
    also probes — useful for packs like the ATLAS brief that
    persist per-kind (``landing`` / ``branding`` / ``page_design``)
    in addition to the legacy ``current`` slot."""


PORTAL_PACK_REGISTRY: tuple[PortalPackSpec, ...] = (
    PortalPackSpec(
        order=1,
        kind="campaign_run_summary",
        singleton_id="current",
        title="Campaign final summary",
        markdown_filenames=("campaign-final-summary.md",),
        blocks_publish_field=None,
        optional=True,
        description="End-to-end run summary emitted by `mkt run-campaign`.",
    ),
    PortalPackSpec(
        order=2,
        kind="campaign_strategy_report",
        singleton_id="current",
        title="Campaign strategy",
        markdown_filenames=("campaign-strategy.md",),
        blocks_publish_field=None,
        optional=False,
        description="The full 20-section strategy report.",
    ),
    PortalPackSpec(
        order=3,
        kind="approval_pack",
        singleton_id="current",
        title="Approval pack",
        markdown_filenames=("approval-pack.md",),
        blocks_publish_field="blocks_publish",
        optional=False,
        description="Approval checklist + posture (may block publish).",
    ),
    PortalPackSpec(
        order=4,
        kind="creative_asset_pack",
        singleton_id="current",
        title="Creative pack",
        markdown_filenames=("creative-pack.md",),
        blocks_publish_field="blocks_publish",
        optional=False,
        description="Approved creative variants per channel.",
    ),
    PortalPackSpec(
        order=5,
        kind="visual_direction_pack",
        singleton_id="current",
        title="Visual direction pack",
        markdown_filenames=("visual-direction-pack.md",),
        blocks_publish_field="blocks_publish",
        optional=False,
        description="Style guide + per-piece visual direction.",
    ),
    PortalPackSpec(
        order=6,
        kind="campaign_execution_task_pack",
        singleton_id="current",
        title="Campaign execution tasks",
        markdown_filenames=("campaign-execution-tasks.md",),
        blocks_publish_field=None,
        optional=True,
        description="Operational task pack (Notion-shaped).",
    ),
    PortalPackSpec(
        order=7,
        kind="notion_sync_plan",
        singleton_id="current",
        title="Notion sync plan",
        markdown_filenames=("notion-sync-plan.md",),
        blocks_publish_field=None,
        optional=True,
        description="Dry preview of the Notion shape — not pushed.",
    ),
    PortalPackSpec(
        order=8,
        kind="n8n_execution_payload",
        singleton_id="current",
        title="n8n execution plan",
        markdown_filenames=("n8n-execution-plan.md",),
        blocks_publish_field=None,
        optional=True,
        description="Dry preview of the n8n payload — not pushed.",
    ),
    PortalPackSpec(
        order=9,
        kind="image_generation_job_pack",
        singleton_id="current",
        title="Image generation jobs",
        markdown_filenames=("image-generation-jobs.md",),
        blocks_publish_field="blocks_publish",
        optional=True,
        description="Job specs for image providers — NOT generated.",
    ),
    PortalPackSpec(
        order=10,
        kind="image_provider_recommendation_pack",
        singleton_id="current",
        title="Image provider plan",
        markdown_filenames=("image-provider-plan.md",),
        blocks_publish_field="blocks_publish",
        optional=True,
        description="Provider scoring + dry-run receipts.",
    ),
    PortalPackSpec(
        order=11,
        kind="optimization_recommendation_pack",
        singleton_id="current",
        title="Analytics recommendations",
        markdown_filenames=("optimization-recommendations.md",),
        blocks_publish_field=None,
        optional=True,
        description="Optimization recommendations from imported metrics.",
    ),
    PortalPackSpec(
        order=12,
        kind="campaign_feedback_pack",
        singleton_id="current",
        title="Campaign feedback pack",
        markdown_filenames=("campaign-feedback-pack.md",),
        blocks_publish_field=None,
        optional=True,
        description="Feedback derived from analytics + ads bridge (optional).",
    ),
    PortalPackSpec(
        order=13,
        kind="next_campaign_iteration_plan",
        singleton_id="current",
        title="Next campaign iteration plan",
        markdown_filenames=("next-campaign-iteration-plan.md",),
        blocks_publish_field=None,
        optional=True,
        description="Suggested next-cycle iteration.",
    ),
    PortalPackSpec(
        order=14,
        kind="atlas_handoff_brief",
        singleton_id="current",
        title="ATLAS bridge briefs",
        markdown_filenames=(
            "atlas-landing-brief.md",
            "atlas-branding-brief.md",
            "atlas-page-design-brief.md",
        ),
        blocks_publish_field="blocks_publish",
        optional=True,
        description=(
            "Handoff briefs for ATLAS (landing / branding / "
            "page_design). Each kind persists separately; "
            "``current`` mirrors the most recent write."
        ),
        extra_singleton_ids=("landing", "branding", "page_design"),
    ),
)
"""Registry consumed by :mod:`portal.app`, the pack loader, and the
checklist. The portal must not surface any kind that is not in
this tuple."""


def iter_pack_specs() -> tuple[PortalPackSpec, ...]:
    """Stable, sorted view of the registry (already sorted, but the
    helper makes the contract explicit)."""
    return tuple(sorted(PORTAL_PACK_REGISTRY, key=lambda s: s.order))


__all__ = ["PORTAL_PACK_REGISTRY", "PortalPackSpec", "iter_pack_specs"]
