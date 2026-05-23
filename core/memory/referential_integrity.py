"""Pure referential integrity helpers.

The Pydantic domain model (MKT-1B) deliberately does NOT enforce cross-entity
references (ADR 0002, D-2.7). Those checks live here so they can be applied
selectively by callers (a future repository layer, a CLI ``check`` command,
CI, etc.) without forcing every model construction to hit storage.

This module is **pure**: it reads through the :class:`Memory` interface but
never writes, never raises domain exceptions, never mutates anything.
Violations are returned as a list of :class:`MissingReference` records.

The reference map is hardcoded here on purpose (ADR 0004, D-4.7). Adding a
new reference between entities requires updating :data:`REFERENCE_MAP` and a
test in ``tests/memory/test_referential_integrity.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import Memory

# Every entity kind known to the domain. Kinds without rules below
# (e.g. ``evidence``, ``channel``, ``offer``) are reachable from other entities
# but do not themselves carry outbound references.
ALL_KINDS: tuple[str, ...] = (
    "client",
    "brief",
    "brand",
    "audience",
    "persona",
    "competitor",
    "offer",
    "positioning",
    "campaign",
    "channel",
    "asset",
    "claim",
    "evidence",
    "metric",
    "footprint",
    "backlog",
    "report",
)


@dataclass(frozen=True)
class ReferenceRule:
    """One outbound reference rule on an entity kind.

    Attributes:
        field: name of the field on the source entity that holds the reference.
        target_kind: kind the field points to.
        is_list: True if the field is a list of ids, False for a single id.
        required: True if the field must be present and non-empty.
    """

    field: str
    target_kind: str
    is_list: bool = False
    required: bool = False


@dataclass(frozen=True)
class MissingReference:
    """A reference that does not resolve to an existing entity."""

    source_kind: str
    source_id: str
    field_path: str
    target_kind: str
    target_id: str
    reason: str = "missing"


# Reference map — keep in sync with the domain model (MKT-1B).
# Entities not listed here are assumed to have no outbound references.
REFERENCE_MAP: dict[str, list[ReferenceRule]] = {
    "client": [
        ReferenceRule("brand_id", "brand"),
    ],
    "brief": [
        ReferenceRule("audience_ids", "audience", is_list=True),
    ],
    "brand": [
        ReferenceRule("logo_asset_ids", "asset", is_list=True),
    ],
    "audience": [
        ReferenceRule("persona_ids", "persona", is_list=True),
    ],
    "persona": [
        ReferenceRule("audience_id", "audience", required=True),
    ],
    "offer": [
        ReferenceRule("target_audience_ids", "audience", is_list=True),
    ],
    "positioning": [
        ReferenceRule("target_audience_ids", "audience", is_list=True),
    ],
    "campaign": [
        ReferenceRule("brief_id", "brief"),
        ReferenceRule("audience_ids", "audience", is_list=True),
        ReferenceRule("channel_ids", "channel", is_list=True),
        ReferenceRule("asset_ids", "asset", is_list=True),
        ReferenceRule("offer_ids", "offer", is_list=True),
    ],
    "asset": [
        ReferenceRule("campaign_id", "campaign"),
        ReferenceRule("claim_ids", "claim", is_list=True),
    ],
    "claim": [
        ReferenceRule("evidence_ids", "evidence", is_list=True),
    ],
    "footprint": [
        ReferenceRule("metric_ids", "metric", is_list=True),
    ],
    "backlog": [
        ReferenceRule("related_campaign_id", "campaign"),
        ReferenceRule("related_audience_ids", "audience", is_list=True),
    ],
    "report": [
        ReferenceRule("metric_ids", "metric", is_list=True),
        ReferenceRule("campaign_ids", "campaign", is_list=True),
    ],
}


@dataclass(frozen=True)
class _SourceId:
    """Best-effort identification of the source entity for error reporting."""

    explicit_id: str | None = None
    fallback_id: str = "<unknown>"

    def resolve(self) -> str:
        return self.explicit_id or self.fallback_id


def _entity_id_of(data: dict[str, Any]) -> str:
    """Pick the most likely id field of an entity payload.

    Prefers ``id``, falls back to ``slug`` (Client uses ``slug`` instead of
    ``id``). Returns ``"<unknown>"`` if neither is present.
    """
    return str(data.get("id") or data.get("slug") or "<unknown>")


def find_missing_references(
    memory: Memory,
    client_slug: str,
    kind: str,
    entity_data: dict[str, Any],
) -> list[MissingReference]:
    """Return every unresolved outbound reference for one entity.

    Returns ``[]`` when:
    - the kind has no rules in :data:`REFERENCE_MAP`, or
    - every referenced id exists in the backend.
    """
    rules = REFERENCE_MAP.get(kind, [])
    if not rules:
        return []

    source_id = _entity_id_of(entity_data)
    out: list[MissingReference] = []

    for rule in rules:
        raw = entity_data.get(rule.field)

        if rule.is_list:
            ids: list[str] = list(raw) if raw else []
            if rule.required and not ids:
                out.append(
                    MissingReference(
                        source_kind=kind,
                        source_id=source_id,
                        field_path=rule.field,
                        target_kind=rule.target_kind,
                        target_id="",
                        reason="required_field_empty",
                    )
                )
                continue
            for i, target_id in enumerate(ids):
                if not target_id:
                    out.append(
                        MissingReference(
                            source_kind=kind,
                            source_id=source_id,
                            field_path=f"{rule.field}[{i}]",
                            target_kind=rule.target_kind,
                            target_id="",
                            reason="empty_id",
                        )
                    )
                    continue
                if not memory.exists(client_slug, rule.target_kind, str(target_id)):
                    out.append(
                        MissingReference(
                            source_kind=kind,
                            source_id=source_id,
                            field_path=f"{rule.field}[{i}]",
                            target_kind=rule.target_kind,
                            target_id=str(target_id),
                        )
                    )
        else:
            if raw in (None, ""):
                if rule.required:
                    out.append(
                        MissingReference(
                            source_kind=kind,
                            source_id=source_id,
                            field_path=rule.field,
                            target_kind=rule.target_kind,
                            target_id="",
                            reason="required_field_empty",
                        )
                    )
                continue
            if not memory.exists(client_slug, rule.target_kind, str(raw)):
                out.append(
                    MissingReference(
                        source_kind=kind,
                        source_id=source_id,
                        field_path=rule.field,
                        target_kind=rule.target_kind,
                        target_id=str(raw),
                    )
                )

    return out


def check_client_integrity(memory: Memory, client_slug: str) -> list[MissingReference]:
    """Walk every kind in :data:`ALL_KINDS` and aggregate missing references.

    Equivalent to looping :func:`find_missing_references` over every entity.
    Order is stable: by kind in :data:`ALL_KINDS`, then by entity id within
    each kind.
    """
    issues: list[MissingReference] = []
    for kind in ALL_KINDS:
        for entity in memory.list(client_slug, kind):
            issues.extend(find_missing_references(memory, client_slug, kind, entity))
    return issues


__all__ = [
    "ALL_KINDS",
    "REFERENCE_MAP",
    "ReferenceRule",
    "MissingReference",
    "find_missing_references",
    "check_client_integrity",
]
