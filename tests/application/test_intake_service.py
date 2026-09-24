"""Tests for the intake application service
(architecture/application-service-boundary).

Covers both entry points: :func:`parse_and_validate` (the pre-context,
tenant-resolution step — see the service module's docstring for why it
exists) and :func:`submit_intake` (the ctx-taking, side-effecting step).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.intake import (
    IntakeParseError,
    parse_and_validate,
    submit_intake,
)
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _raw_intake() -> dict:
    return json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))


def _ctx(tmp_path: Path, client: str) -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )


# ---------- parse_and_validate ----------

def test_parse_and_validate_resolves_slug() -> None:
    intake, validation = parse_and_validate(_raw_intake())
    assert validation.client_slug == "acme-bootstrapped"
    assert intake.schema_version == "client-intake.v1"


def test_parse_and_validate_rejects_malformed_input() -> None:
    with pytest.raises(IntakeParseError):
        parse_and_validate({"not": "a valid intake shape"})


# ---------- submit_intake happy path ----------

def test_submit_intake_persists_and_writes_outputs(tmp_path: Path) -> None:
    intake, validation = parse_and_validate(_raw_intake())
    ctx = _ctx(tmp_path, validation.client_slug)
    result = submit_intake(ctx, intake=intake, validation=validation)
    assert result.ok

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists(validation.client_slug, "client_intake", "current")
    assert mem.exists(validation.client_slug, "intake_validation", "current")

    out_dir = tmp_path / "out" / validation.client_slug
    assert (out_dir / "intake.json").exists()
    assert (out_dir / "intake-summary.md").exists()
    assert (out_dir / "brief.json").exists()  # can_normalize is True for this fixture


def test_submit_intake_writes_audit_event(tmp_path: Path) -> None:
    intake, validation = parse_and_validate(_raw_intake())
    ctx = _ctx(tmp_path, validation.client_slug)
    submit_intake(ctx, intake=intake, validation=validation)

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events(validation.client_slug)
    intake_events = [e for e in events if "intake" in e.payload]
    assert len(intake_events) == 1
    assert intake_events[0].payload["intake"]["action"] == "created"


# ---------- error mapping ----------

def test_submit_intake_rejects_client_slug_mismatch(tmp_path: Path) -> None:
    intake, validation = parse_and_validate(_raw_intake())
    ctx = _ctx(tmp_path, "a-completely-different-slug")
    result = submit_intake(ctx, intake=intake, validation=validation)
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def _minimal_raw_intake() -> dict:
    return {"schema_version": "client-intake.v1", "client_name": "Acme"}


def test_submit_intake_strict_mode_blocks_on_critical(tmp_path: Path) -> None:
    intake, validation = parse_and_validate(_minimal_raw_intake())
    assert validation.missing_critical_count > 0

    ctx = _ctx(tmp_path, validation.client_slug)
    result = submit_intake(ctx, intake=intake, validation=validation, strict=True)
    assert not result.ok
    assert result.error.code is ErrorCode.POLICY_BLOCKED

    # Files were still written even though --strict rejected the result
    # (matches the CLI's long-standing "reviewer can still fix" contract).
    out_dir = tmp_path / "out" / validation.client_slug
    assert (out_dir / "intake.json").exists()
    assert (out_dir / "intake-summary.md").exists()


def test_submit_intake_without_strict_succeeds_despite_critical(tmp_path: Path) -> None:
    intake, validation = parse_and_validate(_minimal_raw_intake())
    assert validation.missing_critical_count > 0

    ctx = _ctx(tmp_path, validation.client_slug)
    result = submit_intake(ctx, intake=intake, validation=validation, strict=False)
    assert result.ok


# ---------- tenant isolation ----------

def test_two_intakes_different_slugs_do_not_collide(tmp_path: Path) -> None:
    intake, validation = parse_and_validate(_raw_intake())
    ctx = _ctx(tmp_path, validation.client_slug)
    assert submit_intake(ctx, intake=intake, validation=validation).ok

    raw2 = _raw_intake()
    raw2["client_slug_override"] = "second-client"
    intake2, validation2 = parse_and_validate(raw2)
    assert validation2.client_slug == "second-client"
    ctx2 = _ctx(tmp_path, validation2.client_slug)
    assert submit_intake(ctx2, intake=intake2, validation=validation2).ok

    mem = JsonFileMemory(tmp_path / "mem")
    first = mem.get(validation.client_slug, "client_intake", "current")
    second = mem.get(validation2.client_slug, "client_intake", "current")
    assert first["client_slug_override"] != second.get("client_slug_override")
