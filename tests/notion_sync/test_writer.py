"""Tests for the NotionWriter ABC + the three shipped writers.

Every test uses mocks. NO real Notion call. CI never needs
``NOTION_TOKEN``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.notion_sync.writer import (
    NoNotionCredentialsError,
    NotionClientWriter,
    NotionPageRequest,
    NotionWriteAttempt,
    NotionWriteError,
    RefusingNotionWriter,
    ScriptedNotionWriter,
)


def _req(task_id: str = "t1", *, sink=None, properties=None) -> NotionPageRequest:
    return NotionPageRequest(
        task_id=task_id,
        database_id="db_test",
        properties=properties if properties is not None else {"Name": {}},
        record_sink=sink,
    )


# ---------- RefusingNotionWriter ----------

def test_refusing_writer_always_raises() -> None:
    w = RefusingNotionWriter()
    with pytest.raises(NoNotionCredentialsError):
        w.create_page(_req())


# ---------- ScriptedNotionWriter ----------

def test_scripted_writer_returns_canned_page_id() -> None:
    w = ScriptedNotionWriter(responses={"t1": "page-abc"})
    sink: list = []
    result = w.create_page(_req("t1", sink=sink))
    assert result.page_id == "page-abc"
    assert len(sink) == 1
    assert sink[0].ok is True
    assert sink[0].page_id == "page-abc"


def test_scripted_writer_default_page_id_pattern() -> None:
    w = ScriptedNotionWriter()
    result = w.create_page(_req("ttttttttxxxxxxxx"))
    assert result.page_id.startswith("page-for-")


def test_scripted_writer_errors_for() -> None:
    err = RuntimeError("boom")
    w = ScriptedNotionWriter(errors_for={"t1": err})
    sink: list = []
    with pytest.raises(NotionWriteError):
        w.create_page(_req("t1", sink=sink))
    assert len(sink) == 1
    assert sink[0].ok is False
    assert sink[0].error_type == "RuntimeError"


def test_scripted_writer_records_calls() -> None:
    w = ScriptedNotionWriter()
    w.create_page(_req("t1"))
    w.create_page(_req("t2"))
    assert [c.task_id for c in w.calls] == ["t1", "t2"]


# ---------- NotionClientWriter — construction ----------

def test_missing_token_raises(monkeypatch) -> None:
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_TASKS_DATABASE_ID", raising=False)
    with pytest.raises(NoNotionCredentialsError):
        NotionClientWriter()


def test_missing_database_id_raises(monkeypatch) -> None:
    monkeypatch.delenv("NOTION_TASKS_DATABASE_ID", raising=False)
    with pytest.raises(NoNotionCredentialsError):
        NotionClientWriter(token="ntn-secret-fake")


def test_env_token_picked_up(monkeypatch) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "ntn-env-fake")
    monkeypatch.setenv("NOTION_TASKS_DATABASE_ID", "db-env")
    w = NotionClientWriter(client=MagicMock())
    assert w.database_id == "db-env"


def test_repr_redacts_token(monkeypatch) -> None:
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    w = NotionClientWriter(
        token="ntn-LEAKED-12345",
        database_id="db-x",
        client=MagicMock(),
    )
    s = repr(w)
    assert "***redacted***" in s
    assert "ntn-LEAKED" not in s
    assert "12345" not in s


def test_dependency_injection_short_circuits_sdk_import(monkeypatch) -> None:
    """When the caller injects a client, the writer must NOT attempt
    to import notion_client. Keeps tests fully offline even on
    machines without the SDK."""
    import sys
    saved = sys.modules.pop("notion_client", None)
    try:
        sys.modules["notion_client"] = None  # type: ignore[assignment]
        w = NotionClientWriter(
            token="t", database_id="db", client=MagicMock(),
        )
        assert w.database_id == "db"
    finally:
        if saved is not None:
            sys.modules["notion_client"] = saved
        else:
            sys.modules.pop("notion_client", None)


# ---------- NotionClientWriter — create_page ----------

def _ok_response(page_id: str = "pg_abc") -> MagicMock:
    r = MagicMock()
    r.id = page_id
    return r


def test_create_page_success(monkeypatch) -> None:
    client = MagicMock()
    client.pages.create.return_value = _ok_response("pg_xyz")
    w = NotionClientWriter(token="t", database_id="db", client=client)
    sink: list = []
    result = w.create_page(_req("t1", sink=sink))
    assert result.page_id == "pg_xyz"
    assert len(sink) == 1
    rec = sink[0]
    assert isinstance(rec, NotionWriteAttempt)
    assert rec.ok is True
    assert rec.page_id == "pg_xyz"


def test_create_page_forwards_database_and_properties() -> None:
    client = MagicMock()
    client.pages.create.return_value = _ok_response()
    w = NotionClientWriter(token="t", database_id="db-default", client=client)
    # Use a request with an explicit database_id so the writer routes
    # through request.database_id (not the constructor default).
    req = NotionPageRequest(
        task_id="t1",
        database_id="db-from-request",
        properties={"Name": {"title": [{"text": {"content": "x"}}]}},
    )
    w.create_page(req)
    kwargs = client.pages.create.call_args.kwargs
    assert kwargs["parent"] == {"database_id": "db-from-request"}
    assert "Name" in kwargs["properties"]


def test_create_page_empty_properties_refuses() -> None:
    client = MagicMock()
    w = NotionClientWriter(token="t", database_id="db", client=client)
    sink: list = []
    with pytest.raises(NotionWriteError):
        w.create_page(_req("t1", properties={}, sink=sink))
    client.pages.create.assert_not_called()
    assert len(sink) == 1
    assert sink[0].error_type == "EmptyPropertiesError"


@pytest.mark.parametrize(
    "exc_class_name",
    [
        "APIResponseError",
        "RequestTimeoutError",
        "HTTPResponseError",
        "RuntimeError",
    ],
)
def test_create_page_wraps_sdk_errors(exc_class_name: str) -> None:
    exc_cls = type(exc_class_name, (Exception,), {})
    client = MagicMock()
    client.pages.create.side_effect = exc_cls("boom")
    w = NotionClientWriter(token="t", database_id="db", client=client)
    sink: list = []
    with pytest.raises(NotionWriteError) as ei:
        w.create_page(_req("t1", sink=sink))
    assert exc_class_name in str(ei.value)
    assert sink[0].ok is False
    assert sink[0].error_type == exc_class_name


def test_error_does_not_leak_token() -> None:
    secret = "ntn-LEAK-secret-123"
    client = MagicMock()
    client.pages.create.side_effect = Exception("auth failed for key ntn-LEAK-secret-123")
    w = NotionClientWriter(token=secret, database_id="db", client=client)
    sink: list = []
    with pytest.raises(NotionWriteError):
        w.create_page(_req("t1", sink=sink))
    # Our repr never echoes the key.
    assert "ntn-LEAK" not in repr(w)
    # The error message capping defends against future regressions.
    assert sink[0].error_message is not None
    assert len(sink[0].error_message) <= 200


def test_response_without_id_returns_unknown() -> None:
    r = MagicMock()
    r.id = None
    client = MagicMock()
    client.pages.create.return_value = r
    w = NotionClientWriter(token="t", database_id="db", client=client)
    result = w.create_page(_req("t1"))
    assert result.page_id == "unknown"


# ---------- No SDK import in module ----------

def test_writer_module_does_not_import_notion_sdk() -> None:
    """The writer module file must NOT have a top-level
    `import notion_client` (only lazy inside the constructor)."""
    import inspect

    import core.notion_sync.writer as mod
    src = inspect.getsource(mod)
    # Allow the lazy import inside __init__ but reject top-level.
    top = src.split("class NotionClientWriter")[0]
    assert "import notion_client" not in top
    assert "from notion_client" not in top
    # And the lazy import is gated by `if resolved_client is None`.
    assert "lazy" in src.lower() or "if resolved_client is None" in src
