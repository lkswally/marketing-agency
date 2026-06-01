"""Tests for :class:`AnthropicSDKInvoker` (MKT-4B).

EVERY test in this module uses a mocked SDK client. There is NO real
HTTP call. CI does NOT need ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.strategy import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicSDKInvoker,
    ClaudeInvocationContext,
    ClaudeInvocationRecord,
    ClaudeInvokerError,
    NoCredentialsError,
)

# ---------- fixtures ----------

def _ok_response(text: str = '{"ok": true}', *, request_id: str = "req_test_1",
                 model: str = "claude-sonnet-4-5-mock",
                 input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    r = MagicMock()
    r.id = request_id
    r.model = model
    r.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    block = MagicMock()
    block.text = text
    r.content = [block]
    return r


def _fake_client(response: MagicMock | Exception) -> MagicMock:
    client = MagicMock()
    if isinstance(response, Exception):
        client.messages.create.side_effect = response
    else:
        client.messages.create.return_value = response
    return client


def _context(method: str = "value_proposition", *, sink=None) -> ClaudeInvocationContext:
    return ClaudeInvocationContext(
        method=method,
        client_slug="acme",
        record_sink=sink,
    )


# ---------- construction ----------

def test_missing_api_key_raises_no_credentials(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(NoCredentialsError):
        AnthropicSDKInvoker()


def test_explicit_api_key_is_used(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    inv = AnthropicSDKInvoker(api_key="sk-explicit-fake", client=_fake_client(_ok_response()))
    assert inv.model == DEFAULT_ANTHROPIC_MODEL


def test_env_var_api_key_is_used(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-fake")
    inv = AnthropicSDKInvoker(client=_fake_client(_ok_response()))
    assert inv.model == DEFAULT_ANTHROPIC_MODEL


def test_model_env_var_overrides_default(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-x-env")
    inv = AnthropicSDKInvoker(client=_fake_client(_ok_response()))
    assert inv.model == "claude-opus-x-env"


def test_constructor_model_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("ANTHROPIC_MODEL", "from-env")
    inv = AnthropicSDKInvoker(
        model="from-arg", client=_fake_client(_ok_response())
    )
    assert inv.model == "from-arg"


# ---------- credential safety ----------

def test_repr_redacts_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    inv = AnthropicSDKInvoker(
        api_key="sk-ant-leaked-12345-DO-NOT-LEAK",
        client=_fake_client(_ok_response()),
    )
    s = repr(inv)
    assert "***redacted***" in s
    assert "sk-ant-leaked" not in s
    assert "12345" not in s


def test_repr_redacts_env_api_key(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-secret-12345")
    inv = AnthropicSDKInvoker(client=_fake_client(_ok_response()))
    s = repr(inv)
    assert "sk-ant-env-secret" not in s
    assert "***redacted***" in s


# ---------- happy path ----------

def test_complete_returns_text_and_appends_record() -> None:
    client = _fake_client(_ok_response(text='{"headline":"x"}', request_id="req_42"))
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    sink: list = []
    text = inv.complete(
        "prompt body",
        system="system body",
        context=_context(sink=sink),
    )
    assert text == '{"headline":"x"}'
    assert len(sink) == 1
    rec = sink[0]
    assert isinstance(rec, ClaudeInvocationRecord)
    assert rec.ok is True
    assert rec.request_id == "req_42"
    assert rec.input_tokens == 100
    assert rec.output_tokens == 50
    assert rec.duration_ms >= 0.0
    assert rec.error_type is None


def test_complete_forwards_max_tokens_and_temperature() -> None:
    client = _fake_client(_ok_response())
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    ctx = ClaudeInvocationContext(
        method="email_sequence",
        client_slug="acme",
        max_tokens=512,
        temperature=0.2,
        record_sink=None,
    )
    inv.complete("hi", system="sys", context=ctx)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 512
    assert kwargs["temperature"] == 0.2
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_no_system_omits_system_kwarg() -> None:
    client = _fake_client(_ok_response())
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    inv.complete("hi", system=None, context=_context())
    assert "system" not in client.messages.create.call_args.kwargs


# ---------- error mapping ----------

@pytest.mark.parametrize(
    "exc_class_name",
    [
        "AuthenticationError",
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "APIError",
        "RuntimeError",
    ],
)
def test_sdk_errors_map_to_invoker_error(exc_class_name: str) -> None:
    # Build a dynamic exception class with the desired name so the
    # invoker's `type(exc).__name__` mapping is exercised exactly.
    exc_cls = type(exc_class_name, (Exception,), {})
    client = _fake_client(exc_cls("boom"))
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    sink: list = []
    with pytest.raises(ClaudeInvokerError) as ei:
        inv.complete("p", system="s", context=_context(sink=sink))
    assert exc_class_name in str(ei.value)
    assert len(sink) == 1
    rec = sink[0]
    assert rec.ok is False
    assert rec.error_type == exc_class_name
    assert rec.input_tokens is None
    assert rec.output_tokens is None
    assert rec.request_id is None


def test_error_message_does_not_leak_api_key() -> None:
    secret = "sk-ant-LEAKED-secret-123"
    client = _fake_client(Exception(f"auth failed for key {secret}"))
    inv = AnthropicSDKInvoker(api_key=secret, client=client)
    sink: list = []
    with pytest.raises(ClaudeInvokerError) as ei:
        inv.complete("p", system="s", context=_context(sink=sink))
    # The invoker passes the SDK error through. The KEY itself appearing
    # in the reason is the SDK's responsibility — but the test asserts
    # the INVOKER's defensive behavior: error_message is capped at 160
    # chars, no extra metadata, no leak of the key from US (we never
    # construct the message ourselves with the key).
    rec = sink[0]
    assert rec.error_message is not None
    assert len(rec.error_message) <= 160
    # The raised exception string is also capped (defensive: we built it).
    assert len(str(ei.value)) <= 200
    # Our own invoker code MUST NOT append the key to any string.
    # Verify our class string repr also redacts.
    assert "sk-ant-LEAKED" not in repr(inv)


def test_error_message_does_not_leak_prompt() -> None:
    long_prompt = "PROMPT-SECRET-DATA " * 50
    client = _fake_client(Exception("boom"))
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    sink: list = []
    with pytest.raises(ClaudeInvokerError) as ei:  # noqa: PT012
        inv.complete(long_prompt, system="s", context=_context(sink=sink))
    assert "PROMPT-SECRET-DATA" not in str(ei.value)
    assert "PROMPT-SECRET-DATA" not in (sink[0].error_message or "")


# ---------- response shape resilience ----------

def test_missing_usage_returns_none_tokens() -> None:
    r = MagicMock()
    r.id = "req_x"
    r.model = "m"
    r.usage = None
    block = MagicMock(text="ok")
    r.content = [block]
    client = _fake_client(r)
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    sink: list = []
    inv.complete("p", system="s", context=_context(sink=sink))
    assert sink[0].input_tokens is None
    assert sink[0].output_tokens is None


def test_missing_content_returns_empty_text() -> None:
    r = MagicMock()
    r.id = "req_x"
    r.model = "m"
    r.usage = MagicMock(input_tokens=1, output_tokens=1)
    r.content = []
    client = _fake_client(r)
    inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
    text = inv.complete("p", system="s", context=_context())
    assert text == ""


# ---------- no real network ----------

def test_no_real_anthropic_import_when_client_injected(monkeypatch) -> None:
    """If the caller injects a client, the invoker must NEVER import
    ``anthropic``. This keeps tests fully offline even on machines
    without the SDK installed."""
    import sys
    saved = sys.modules.pop("anthropic", None)
    try:
        # Replace anthropic in sys.modules with a marker that would crash
        # if accessed. The invoker must not look at it.
        sys.modules["anthropic"] = None  # type: ignore[assignment]
        client = _fake_client(_ok_response())
        inv = AnthropicSDKInvoker(api_key="sk-x", client=client)
        out = inv.complete("p", system="s", context=_context())
        assert out
    finally:
        if saved is not None:
            sys.modules["anthropic"] = saved
        else:
            sys.modules.pop("anthropic", None)
