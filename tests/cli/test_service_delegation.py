"""Behavioral proof that the migrated CLI commands call THROUGH their
application service rather than reimplementing domain orchestration
themselves (architecture/application-service-boundary, Phase 9).

Each test monkeypatches the service function to a stub that returns a
canned :class:`OperationResult` WITHOUT touching memory, factories, or
any domain module — then asserts the CLI's stdout/exit-code reflects
that stub's data. If a CLI function still did its own domain work (the
pre-migration shape), these stubs would never be reached and either the
test would hang on missing fixtures or the printed payload would not
match the stub's fabricated values. This is deliberately NOT a pure
import/AST check (see test_no_direct_core_domain_calls.py for that) —
it proves the call actually happens at runtime.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from cli.main import main
from core.application.result import Artifact, OperationResult


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


class _Enumish:
    """Minimal stand-in for a StrEnum member — just needs `.value`."""

    def __init__(self, value: str) -> None:
        self.value = value


class _FakeCreativePack:
    pack_id = "fake-creative-pack-id"
    client_slug = "acme"
    report_id = "fake-report-id"
    approval_pack_id = None
    derived_overall_state = _Enumish("needs_review")
    blocks_publish = False
    total_assets = 0
    rule_set_id = "fake-rules"

    def count_by_kind(self) -> dict:
        return {}

    def count_by_state(self) -> dict:
        return {}


def test_build_creatives_calls_through_the_service(tmp_path: Path) -> None:
    fake_pack = _FakeCreativePack()
    stub_result = OperationResult.ok_result(
        data=fake_pack,
        artifacts=[Artifact(path=tmp_path / "out" / "creative-pack.md", kind="markdown")],
    )
    with patch(
        "core.application.services.creative.build_creative_pack", return_value=stub_result,
    ) as mock_service:
        code, text = _run(
            [
                "build-creatives",
                "--client", "acme",
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )
    assert code == 0
    mock_service.assert_called_once()
    payload = json.loads(text)
    assert payload["pack_id"] == "fake-creative-pack-id"
    # No memory root was ever created — proof the CLI never fell back to
    # constructing JsonFileMemory / a factory itself.
    assert not (tmp_path / "mem").exists()


class _FakeVisualPack:
    pack_id = "fake-visual-pack-id"
    client_slug = "acme"
    report_id = "fake-report-id"
    approval_pack_id = None
    creative_pack_id = None
    derived_overall_state = _Enumish("needs_review")
    blocks_publish = False
    total_directions = 0
    total_prompt_variants = 0
    rule_set_id = "fake-rules"

    def count_by_state(self) -> dict:
        return {}

    def count_risks_by_severity(self) -> dict:
        return {}


def test_build_visuals_calls_through_the_service(tmp_path: Path) -> None:
    fake_pack = _FakeVisualPack()
    stub_result = OperationResult.ok_result(data=fake_pack, artifacts=[])
    with patch(
        "core.application.services.visual.build_visual_pack", return_value=stub_result,
    ) as mock_service:
        code, text = _run(
            [
                "build-visuals",
                "--client", "acme",
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )
    assert code == 0
    mock_service.assert_called_once()
    payload = json.loads(text)
    assert payload["pack_id"] == "fake-visual-pack-id"
    assert not (tmp_path / "mem").exists()


class _FakeTaskPack:
    pack_id = "fake-task-pack-id"
    client_slug = "acme"
    report_id = "fake-report-id"
    approval_pack_id = None
    creative_pack_id = None
    visual_pack_id = None
    blocks_publish = False
    total_tasks = 0
    rule_set_id = "fake-rules"

    def count_by_state(self) -> dict:
        return {}

    def count_by_priority(self) -> dict:
        return {}

    def count_by_category(self) -> dict:
        return {}


def test_build_tasks_calls_through_the_service(tmp_path: Path) -> None:
    fake_pack = _FakeTaskPack()
    stub_result = OperationResult.ok_result(data=fake_pack, artifacts=[])
    with patch(
        "core.application.services.tasks.build_task_pack", return_value=stub_result,
    ) as mock_service:
        code, text = _run(
            [
                "build-tasks",
                "--client", "acme",
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )
    assert code == 0
    mock_service.assert_called_once()
    payload = json.loads(text)
    assert payload["pack_id"] == "fake-task-pack-id"
    assert not (tmp_path / "mem").exists()


def test_intake_calls_through_the_service(tmp_path: Path) -> None:
    from core.intake import ClientIntake, IntakeValidationResult

    intake_file = tmp_path / "intake.json"
    intake_file.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )

    from core.domain.base import utcnow

    fake_intake = ClientIntake(schema_version="client-intake.v1", client_name="Acme")
    now = utcnow()
    fake_validation = IntakeValidationResult(
        intake_id="fake-intake-id",
        client_slug="acme-stub",
        is_valid=True,
        can_normalize=False,
        missing_critical_count=0,
        missing_warning_count=0,
        missing_info_count=0,
        created_at=now,
        updated_at=now,
    )
    stub_result = OperationResult.ok_result(data={"intake": fake_intake, "validation": fake_validation})

    with (
        patch(
            "core.application.services.intake.parse_and_validate",
            return_value=(fake_intake, fake_validation),
        ) as mock_parse,
        patch(
            "core.application.services.intake.submit_intake", return_value=stub_result,
        ) as mock_submit,
    ):
        code, text = _run(
            [
                "intake",
                "--file", str(intake_file),
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
            ]
        )
    assert code == 0
    mock_parse.assert_called_once()
    mock_submit.assert_called_once()
    payload = json.loads(text)
    assert payload["client_slug"] == "acme-stub"
    assert not (tmp_path / "mem").exists()
