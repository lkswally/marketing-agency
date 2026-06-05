"""Pre-flight checklist for the portal (MKT-9A).

Aggregates the per-pack load results into a short summary:

- counts: total / OK / MISSING / BLOCKED / ERROR
- required-missing list (blocks Definition-of-Ready)
- blocked list (publish gate)
- error list (operator must inspect)

Pure function over a list of :class:`PackLoadResult` — no
filesystem reads beyond what the loader already did.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pack_loader import PackLoadResult, PackStatus


@dataclass(frozen=True)
class ChecklistResult:
    """One row in the checklist UI."""

    title: str
    status: PackStatus
    optional: bool
    detail: str | None = None


@dataclass
class PreflightChecklist:
    total: int
    ok: int = 0
    missing: int = 0
    blocked: int = 0
    error: int = 0
    required_missing: list[str] = field(default_factory=list)
    blocked_titles: list[str] = field(default_factory=list)
    error_titles: list[str] = field(default_factory=list)
    rows: list[ChecklistResult] = field(default_factory=list)

    @property
    def is_publish_ready(self) -> bool:
        """Publish-ready when no required pack is missing AND no
        pack is blocked. Errors also block — operator must
        inspect them first."""
        return (
            not self.required_missing
            and self.blocked == 0
            and self.error == 0
        )

    @property
    def is_atlas_handoff_ready(self) -> bool:
        """Looser gate: ATLAS handoff only needs the required
        upstream packs (strategy / approval / creative / visual)
        to be present and not blocked."""
        return (
            not self.required_missing
            and self.blocked == 0
        )


def build_preflight_checklist(
    results: list[PackLoadResult],
) -> PreflightChecklist:
    """Aggregate the results into a portable summary."""

    cl = PreflightChecklist(total=len(results))
    for r in results:
        detail = None
        if r.status is PackStatus.OK:
            cl.ok += 1
        elif r.status is PackStatus.MISSING:
            cl.missing += 1
            if not r.spec.optional:
                cl.required_missing.append(r.spec.title)
            detail = "Pack file not found on disk."
        elif r.status is PackStatus.BLOCKED:
            cl.blocked += 1
            cl.blocked_titles.append(r.spec.title)
            detail = "Upstream posture blocks publish."
        elif r.status is PackStatus.ERROR:
            cl.error += 1
            cl.error_titles.append(r.spec.title)
            detail = r.error_message
        cl.rows.append(ChecklistResult(
            title=r.spec.title,
            status=r.status,
            optional=r.spec.optional,
            detail=detail,
        ))
    return cl


__all__ = [
    "ChecklistResult",
    "PreflightChecklist",
    "build_preflight_checklist",
]
