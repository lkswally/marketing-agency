"""Tests for portal.checklist — aggregate per-pack results."""

from __future__ import annotations

from portal.checklist import build_preflight_checklist
from portal.pack_loader import PackLoadResult, PackStatus
from portal.pack_registry import PORTAL_PACK_REGISTRY, PortalPackSpec


def _spec_required() -> PortalPackSpec:
    return next(s for s in PORTAL_PACK_REGISTRY if not s.optional)


def _spec_optional() -> PortalPackSpec:
    return next(s for s in PORTAL_PACK_REGISTRY if s.optional)


def _result(spec: PortalPackSpec, status: PackStatus, **kw) -> PackLoadResult:
    return PackLoadResult(
        spec=spec, status=status,
        data=kw.get("data", {} if status is not PackStatus.MISSING else None),
        markdown_path=None, file_path=None,
        error_message=kw.get("error_message"),
    )


def test_empty_input_yields_zero_total() -> None:
    cl = build_preflight_checklist([])
    assert cl.total == 0
    assert cl.is_publish_ready
    assert cl.is_atlas_handoff_ready


def test_single_ok_required_pack() -> None:
    cl = build_preflight_checklist([
        _result(_spec_required(), PackStatus.OK),
    ])
    assert cl.ok == 1
    assert cl.missing == 0
    assert cl.is_publish_ready


def test_missing_required_pack_blocks_publish_and_handoff() -> None:
    cl = build_preflight_checklist([
        _result(_spec_required(), PackStatus.MISSING),
    ])
    assert cl.missing == 1
    assert cl.required_missing == [_spec_required().title]
    assert not cl.is_publish_ready
    assert not cl.is_atlas_handoff_ready


def test_missing_optional_pack_does_not_block() -> None:
    cl = build_preflight_checklist([
        _result(_spec_optional(), PackStatus.MISSING),
    ])
    assert cl.missing == 1
    assert cl.required_missing == []
    assert cl.is_publish_ready
    assert cl.is_atlas_handoff_ready


def test_blocked_pack_fails_both_gates() -> None:
    cl = build_preflight_checklist([
        _result(_spec_required(), PackStatus.BLOCKED),
    ])
    assert cl.blocked == 1
    assert cl.blocked_titles == [_spec_required().title]
    assert not cl.is_publish_ready
    assert not cl.is_atlas_handoff_ready


def test_error_pack_fails_publish_but_not_necessarily_handoff() -> None:
    """An ERROR row indicates a corrupt file. Publish gate fails;
    ATLAS handoff gate also fails because we can't read the pack
    so its required-status is unknown."""
    cl = build_preflight_checklist([
        _result(_spec_required(), PackStatus.ERROR,
                error_message="JSONDecodeError: line 1"),
    ])
    assert cl.error == 1
    assert cl.error_titles == [_spec_required().title]
    assert not cl.is_publish_ready


def test_rows_carry_detail_text() -> None:
    cl = build_preflight_checklist([
        _result(_spec_required(), PackStatus.OK),
        _result(_spec_optional(), PackStatus.MISSING),
        _result(_spec_required(), PackStatus.BLOCKED),
        _result(_spec_required(), PackStatus.ERROR, error_message="boom"),
    ])
    by_status = {row.status: row for row in cl.rows}
    assert by_status[PackStatus.MISSING].detail == "Pack file not found on disk."
    assert "blocks publish" in by_status[PackStatus.BLOCKED].detail
    assert by_status[PackStatus.ERROR].detail == "boom"


def test_all_optional_present_publishes_ready() -> None:
    results = [
        _result(s, PackStatus.OK) for s in PORTAL_PACK_REGISTRY
    ]
    cl = build_preflight_checklist(results)
    assert cl.ok == len(PORTAL_PACK_REGISTRY)
    assert cl.is_publish_ready
    assert cl.is_atlas_handoff_ready


def test_partial_real_world_scenario() -> None:
    """All required packs present, one optional missing, no blocks."""
    rows: list[PackLoadResult] = []
    for s in PORTAL_PACK_REGISTRY:
        status = PackStatus.MISSING if s.optional and s.order == 11 else PackStatus.OK
        rows.append(_result(s, status))
    cl = build_preflight_checklist(rows)
    assert cl.is_publish_ready
    assert cl.is_atlas_handoff_ready
    assert cl.missing == 1
