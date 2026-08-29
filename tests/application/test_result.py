"""Tests for OperationResult / OperationError (MKT-11A)."""

from __future__ import annotations

from pathlib import Path

from core.application import Artifact, ErrorCode, OperationResult, OperationWarning


def test_ok_result_defaults() -> None:
    r = OperationResult.ok_result()
    assert r.ok is True
    assert r.data is None
    assert r.artifacts == []
    assert r.warnings == []
    assert r.error is None
    assert r.operation_id  # auto-generated


def test_ok_result_with_data_and_artifacts() -> None:
    art = Artifact(path=Path("out/x.md"), kind="markdown")
    r = OperationResult.ok_result(data={"x": 1}, artifacts=[art], audit_event_id="h1")
    assert r.ok is True
    assert r.data == {"x": 1}
    assert r.artifacts == [art]
    assert r.audit_event_id == "h1"


def test_error_result() -> None:
    r = OperationResult.error_result(
        code=ErrorCode.NOT_FOUND, message="missing", remediation="do X",
    )
    assert r.ok is False
    assert r.error is not None
    assert r.error.code is ErrorCode.NOT_FOUND
    assert r.error.message == "missing"
    assert r.error.remediation == "do X"


def test_warning_carried_on_ok_result() -> None:
    w = OperationWarning(code="already_done", message="no-op")
    r = OperationResult.ok_result(warnings=[w])
    assert r.ok is True
    assert r.warnings == [w]


def test_artifact_dry_run_flag() -> None:
    art = Artifact(path=Path("out/x.md"), kind="markdown", would_write=True)
    assert art.would_write is True
