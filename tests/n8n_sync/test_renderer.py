"""Markdown renderer tests for the n8n payload."""

from __future__ import annotations

from datetime import UTC, datetime

from core.n8n_sync import (
    N8nAction,
    N8nActionStatus,
    N8nActionType,
    N8nExecutionPayload,
    N8nPayloadStats,
    render_markdown_payload,
)


def _payload(**overrides):
    base = dict(
        client_slug="acme-saas",
        actions=[],
        stats=N8nPayloadStats(total_actions=0, planned=0, blocked=0),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return N8nExecutionPayload(**base)


def test_renders_dry_run_warning() -> None:
    md = render_markdown_payload(_payload())
    assert "DRY RUN" in md
    assert "No se llamó a n8n" in md


def test_header_with_payload_id() -> None:
    p = _payload()
    md = render_markdown_payload(p)
    assert p.payload_id in md
    assert "n8n-execution-payload.v1" in md


def test_summary_counts_rendered() -> None:
    actions = [
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="email_drafts",
            payload={"x": 1},
        ),
        N8nAction(
            action_type=N8nActionType.SOCIAL_POST_DRAFT,
            target_webhook="social_drafts",
            status=N8nActionStatus.BLOCKED,
            blocked_reason="approval",
            payload={"y": 2},
        ),
    ]
    p = _payload(
        actions=actions,
        stats=N8nPayloadStats(total_actions=2, planned=1, blocked=1, by_type={
            "email_draft": 1, "social_post_draft": 1,
        }),
        blocks_publish=True,
    )
    md = render_markdown_payload(p)
    assert "`planned`: 1" in md
    assert "`blocked`: 1" in md
    assert "🛑 `True`" in md  # blocks_publish flag


def test_per_type_section_rendered_when_actions_present() -> None:
    actions = [
        N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            target_webhook="email_drafts",
            source_kind="creative_asset_pack.email",
            source_ref="email-1",
            payload={"subject": "hi", "body": "test"},
        )
    ]
    p = _payload(
        actions=actions,
        stats=N8nPayloadStats(
            total_actions=1, planned=1, blocked=0, by_type={"email_draft": 1}
        ),
    )
    md = render_markdown_payload(p)
    assert "## email_draft (1)" in md
    assert "email_drafts" in md
    # Payload sample rendered.
    assert "subject" in md


def test_empty_payload_has_no_per_type_sections() -> None:
    md = render_markdown_payload(_payload())
    assert "## email_draft" not in md
    assert "## social_post_draft" not in md


def test_blocked_action_rendered_with_reason() -> None:
    actions = [
        N8nAction(
            action_type=N8nActionType.SOCIAL_POST_DRAFT,
            target_webhook="social_drafts",
            status=N8nActionStatus.BLOCKED,
            blocked_reason="approval blocks publish",
            payload={"channel": "x"},
        )
    ]
    p = _payload(
        actions=actions,
        stats=N8nPayloadStats(
            total_actions=1, planned=0, blocked=1, by_type={"social_post_draft": 1}
        ),
        blocks_publish=True,
    )
    md = render_markdown_payload(p)
    assert "approval blocks publish" in md
    assert "🛑 `blocked`" in md


def test_footer_says_no_http_call() -> None:
    md = render_markdown_payload(_payload())
    assert "No HTTP call was made" in md
    assert "No webhook URL was read" in md


def test_renderer_is_pure() -> None:
    p = _payload()
    a = render_markdown_payload(p)
    b = render_markdown_payload(p)
    assert a == b


def test_renderer_source_does_not_read_env_or_http() -> None:
    import inspect

    import core.n8n_sync.renderer as mod
    src = inspect.getsource(mod)
    for forbidden in ("import requests", "import httpx", "os.environ", "urllib"):
        assert forbidden not in src
