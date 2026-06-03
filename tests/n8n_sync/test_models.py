"""Pydantic validation tests for the n8n payload models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.n8n_sync import (
    N8N_EXECUTION_PAYLOAD_VERSION,
    N8nAction,
    N8nActionStatus,
    N8nActionType,
    N8nExecutionPayload,
    N8nPayloadStats,
)


def _now() -> datetime:
    return datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _stats(**overrides) -> N8nPayloadStats:
    base = dict(total_actions=0, planned=0, blocked=0)
    base.update(overrides)
    return N8nPayloadStats(**base)


def _minimal_payload(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "actions": [],
        "stats": _stats().model_dump(mode="json"),
        "created_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


# ---------- N8nAction ----------

def test_action_minimal() -> None:
    a = N8nAction(
        action_type=N8nActionType.TELEGRAM_NOTIFICATION,
        target_webhook="telegram_alerts",
    )
    assert a.status is N8nActionStatus.PLANNED
    assert a.payload == {}


def test_action_blocked_with_reason() -> None:
    a = N8nAction(
        action_type=N8nActionType.EMAIL_DRAFT,
        target_webhook="email_drafts",
        status=N8nActionStatus.BLOCKED,
        blocked_reason="approval blocks publish",
        payload={"asset_id": "x"},
    )
    assert a.status is N8nActionStatus.BLOCKED
    assert a.payload == {"asset_id": "x"}


def test_action_all_types_validate() -> None:
    for t in N8nActionType:
        a = N8nAction(action_type=t, target_webhook="hook")
        assert a.action_type is t


def test_action_webhook_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="x" * 200,
        )


def test_action_blocked_reason_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="hook",
            blocked_reason="x" * 500,
        )


def test_action_has_no_webhook_url_field() -> None:
    """Sanity: the action model MUST NOT have any field that could
    hold a real webhook URL or credential."""
    fields = set(N8nAction.model_fields.keys())
    for forbidden in ("url", "webhook_url", "secret", "token", "api_key"):
        assert forbidden not in fields


# ---------- N8nExecutionPayload ----------

def test_minimal_payload_validates() -> None:
    p = N8nExecutionPayload.model_validate(_minimal_payload())
    assert p.contract_version == N8N_EXECUTION_PAYLOAD_VERSION
    assert p.total_actions == 0
    assert p.blocks_publish is False


def test_payload_round_trip_json() -> None:
    p = N8nExecutionPayload.model_validate(_minimal_payload())
    reloaded = N8nExecutionPayload.from_json(p.to_json())
    assert reloaded.model_dump() == p.model_dump()


def test_payload_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        N8nExecutionPayload.model_validate(
            _minimal_payload(created_at="2026-06-02T12:00:00")
        )


def test_payload_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        N8nExecutionPayload.model_validate(_minimal_payload(client_slug="Bad Slug"))


def test_payload_version_pinned() -> None:
    with pytest.raises(ValidationError):
        N8nExecutionPayload.model_validate(
            _minimal_payload(contract_version="n8n-execution-payload.v2")
        )


def test_payload_extra_field_rejected() -> None:
    data = _minimal_payload()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        N8nExecutionPayload.model_validate(data)


def test_actions_of_type_filter() -> None:
    actions = [
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="hook",
        ).model_dump(mode="json"),
        N8nAction(
            action_type=N8nActionType.SOCIAL_POST_DRAFT,
            target_webhook="hook",
        ).model_dump(mode="json"),
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="hook",
        ).model_dump(mode="json"),
    ]
    p = N8nExecutionPayload.model_validate(_minimal_payload(actions=actions))
    assert len(p.actions_of_type(N8nActionType.EMAIL_DRAFT)) == 2
    assert len(p.actions_of_type(N8nActionType.SOCIAL_POST_DRAFT)) == 1


def test_blocked_actions_helper() -> None:
    actions = [
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="hook",
            status=N8nActionStatus.PLANNED,
        ).model_dump(mode="json"),
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="hook",
            status=N8nActionStatus.BLOCKED,
            blocked_reason="upstream",
        ).model_dump(mode="json"),
    ]
    p = N8nExecutionPayload.model_validate(_minimal_payload(actions=actions))
    blocked = p.blocked_actions()
    assert len(blocked) == 1
    assert blocked[0].status is N8nActionStatus.BLOCKED
