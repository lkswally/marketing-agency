"""Tests for OperationContext (MKT-11A)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.application import OperationContext, OperationRole, OperationSource


def test_defaults() -> None:
    ctx = OperationContext(client_slug="acme")
    assert ctx.root == Path("data/clients")
    assert ctx.outputs_root == Path("outputs")
    assert ctx.actor_id == "unknown"
    assert ctx.role is OperationRole.OPERATOR
    assert ctx.source is OperationSource.CLI
    assert ctx.correlation_id  # non-empty, auto-generated
    assert ctx.requested_at.tzinfo is not None


def test_invalid_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        OperationContext(client_slug="Not_A_Slug!")


def test_short_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        OperationContext(client_slug="a")


def test_context_is_frozen() -> None:
    ctx = OperationContext(client_slug="acme")
    with pytest.raises(ValidationError):
        ctx.client_slug = "other"  # type: ignore[misc]


def test_custom_fields_round_trip(tmp_path: Path) -> None:
    ctx = OperationContext(
        client_slug="acme",
        root=tmp_path / "mem",
        outputs_root=tmp_path / "out",
        actor_id="lucas",
        role=OperationRole.APPROVER,
        source=OperationSource.API,
        correlation_id="corr-1",
    )
    assert ctx.actor_id == "lucas"
    assert ctx.role is OperationRole.APPROVER
    assert ctx.source is OperationSource.API
    assert ctx.correlation_id == "corr-1"


def test_two_contexts_get_distinct_correlation_ids() -> None:
    a = OperationContext(client_slug="acme")
    b = OperationContext(client_slug="acme")
    assert a.correlation_id != b.correlation_id
