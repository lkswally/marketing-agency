"""Validation tests for :class:`ClaudeInvocationRecord` (MKT-4B)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.strategy import ClaudeInvocationRecord


def test_success_record_validates() -> None:
    r = ClaudeInvocationRecord(
        method="value_proposition",
        model="claude-sonnet-4-5-x",
        request_id="req_abc123",
        input_tokens=120,
        output_tokens=80,
        duration_ms=412.5,
        ok=True,
    )
    assert r.ok is True
    assert r.error_type is None
    assert r.error_message is None


def test_failure_record_validates_without_tokens() -> None:
    r = ClaudeInvocationRecord(
        method="email_sequence",
        model="claude-sonnet-4-5-x",
        duration_ms=88.0,
        ok=False,
        error_type="AuthenticationError",
        error_message="invalid api key",
    )
    assert r.ok is False
    assert r.input_tokens is None
    assert r.output_tokens is None
    assert r.request_id is None


def test_negative_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        ClaudeInvocationRecord(
            method="x",
            duration_ms=-1.0,
            ok=False,
        )


def test_negative_tokens_rejected() -> None:
    with pytest.raises(ValidationError):
        ClaudeInvocationRecord(
            method="x",
            duration_ms=1.0,
            ok=True,
            input_tokens=-5,
        )


def test_error_message_truncated_at_160() -> None:
    long = "x" * 500
    with pytest.raises(ValidationError):
        ClaudeInvocationRecord(
            method="x",
            duration_ms=1.0,
            ok=False,
            error_message=long,
        )


def test_no_api_key_field_exists() -> None:
    """Belt-and-suspenders: the record schema MUST NOT have any
    field whose name could leak the API key."""
    fields = set(ClaudeInvocationRecord.model_fields.keys())
    for forbidden in ("api_key", "key", "secret", "token", "credential"):
        assert forbidden not in fields, f"forbidden field present: {forbidden}"
