"""Notion payload renderer tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from core.execution import (
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
    to_notion_payload,
)


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _pack(tasks=None) -> CampaignExecutionTaskPack:
    return CampaignExecutionTaskPack(
        client_slug="acme-saas",
        report_id="r1",
        report_contract_version="campaign-strategy.v1",
        approval_pack_id="ap1",
        approval_pack_contract_version="approval-pack.v1",
        creative_pack_id="cp1",
        creative_pack_contract_version="creative-pack.v1",
        visual_pack_id=None,
        visual_pack_contract_version=None,
        blocks_publish=False,
        upstream_overall_state="draft",
        tasks=tasks or [],
        created_at=_now(),
        updated_at=_now(),
    )


def _task(**kwargs) -> ExecutionTask:
    base = dict(
        title="Sample",
        category=TaskCategory.OPERATIONAL,
        priority=TaskPriority.MEDIUM,
        state=TaskState.TODO,
    )
    base.update(kwargs)
    return ExecutionTask(**base)


def test_payload_top_level_keys() -> None:
    payload = to_notion_payload(_pack())
    assert set(payload.keys()) == {"schema_version", "source_pack", "database", "pages"}
    assert payload["schema_version"] == "notion-export.v1"


def test_source_pack_references() -> None:
    payload = to_notion_payload(_pack())
    src = payload["source_pack"]
    assert src["pack_id"]
    assert src["client_slug"] == "acme-saas"
    assert src["report_id"] == "r1"
    assert src["approval_pack_id"] == "ap1"
    assert src["creative_pack_id"] == "cp1"
    assert src["visual_pack_id"] is None
    assert src["blocks_publish"] is False


def test_database_has_all_required_properties() -> None:
    payload = to_notion_payload(_pack())
    props = payload["database"]["properties"]
    for required in (
        "Name", "Status", "Priority", "Category", "Channel",
        "Asset Kind", "Asset Ref", "Due Date", "Depends On",
        "Owner Hint", "Description", "Blocked Reason", "Task ID",
    ):
        assert required in props


def test_status_select_includes_all_six_states() -> None:
    payload = to_notion_payload(_pack())
    options = payload["database"]["properties"]["Status"]["select"]["options"]
    names = {opt["name"] for opt in options}
    assert names == {"todo", "blocked", "needs_review", "approved", "ready", "done"}


def test_priority_select_includes_three_levels() -> None:
    payload = to_notion_payload(_pack())
    options = payload["database"]["properties"]["Priority"]["select"]["options"]
    names = {opt["name"] for opt in options}
    assert names == {"high", "medium", "low"}


def test_status_options_have_colors() -> None:
    payload = to_notion_payload(_pack())
    options = payload["database"]["properties"]["Status"]["select"]["options"]
    for opt in options:
        assert "color" in opt


def test_page_for_task_has_all_properties() -> None:
    t = _task(
        title="Do the thing",
        description="full description",
        channel="linkedin",
        asset_kind="social_post",
        asset_ref="abc123",
        due_date=date(2026, 7, 1),
        depends_on=["x", "y"],
        owner_hint="copywriter",
    )
    payload = to_notion_payload(_pack(tasks=[t]))
    page = payload["pages"][0]
    props = page["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "Do the thing"
    assert props["Status"]["select"]["name"] == "todo"
    assert props["Priority"]["select"]["name"] == "medium"
    assert props["Category"]["select"]["name"] == "operational"
    assert props["Channel"]["rich_text"][0]["text"]["content"] == "linkedin"
    assert props["Asset Kind"]["rich_text"][0]["text"]["content"] == "social_post"
    assert props["Asset Ref"]["rich_text"][0]["text"]["content"] == "abc123"
    assert props["Due Date"]["date"]["start"] == "2026-07-01"
    assert props["Depends On"]["rich_text"][0]["text"]["content"] == "x, y"
    assert props["Owner Hint"]["rich_text"][0]["text"]["content"] == "copywriter"
    assert props["Task ID"]["rich_text"][0]["text"]["content"]


def test_optional_fields_render_empty_when_absent() -> None:
    t = _task(title="bare")
    payload = to_notion_payload(_pack(tasks=[t]))
    props = payload["pages"][0]["properties"]
    assert props["Channel"]["rich_text"] == []
    assert props["Asset Kind"]["rich_text"] == []
    assert props["Asset Ref"]["rich_text"] == []
    assert props["Due Date"]["date"] is None
    assert props["Owner Hint"]["rich_text"] == []


def test_blocked_task_renders_reason() -> None:
    t = _task(state=TaskState.BLOCKED, blocked_reason="dep on X")
    payload = to_notion_payload(_pack(tasks=[t]))
    props = payload["pages"][0]["properties"]
    assert props["Status"]["select"]["name"] == "blocked"
    assert props["Blocked Reason"]["rich_text"][0]["text"]["content"] == "dep on X"


def test_payload_is_pure() -> None:
    pack = _pack(tasks=[_task(title="a"), _task(title="b")])
    a = to_notion_payload(pack)
    b = to_notion_payload(pack)
    assert a == b


def test_payload_does_not_import_notion_sdk() -> None:
    """Sanity: the renderer must NOT pull the `notion-client` SDK."""
    import sys

    import core.execution.notion_payload as mod
    # The module is already imported; assert anything related is absent.
    for forbidden in ("notion_client", "notion", "requests"):
        assert forbidden not in sys.modules or sys.modules[forbidden].__name__ != forbidden, (
            f"forbidden module {forbidden} should not be imported by notion_payload"
        )
    # Belt-and-suspenders: source doesn't mention these.
    import inspect
    src = inspect.getsource(mod)
    assert "notion_client" not in src
    assert "import requests" not in src
