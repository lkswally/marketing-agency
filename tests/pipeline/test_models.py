"""Pydantic validation tests for the pipeline summary models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.creative.models import CreativeAssetState
from core.pipeline import (
    PIPELINE_RUN_VERSION,
    CampaignRunSummary,
    StageId,
    StageOutcome,
    StageResult,
)


def _now() -> datetime:
    return datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _minimal_summary(**overrides) -> dict:
    base = {
        "contract_version": PIPELINE_RUN_VERSION,
        "run_id": "r1",
        "client_slug": "acme-saas",
        "started_at": _now().isoformat(),
        "finished_at": _now().isoformat(),
        "overall_state": "draft",
        "blocks_publish": False,
        "intake_critical_count": 0,
        "intake_warning_count": 0,
        "intake_info_count": 0,
        "stages": [],
        "rule_set_id": "pipeline-default.v1",
    }
    base.update(overrides)
    return base


# ---------- CampaignRunSummary ----------

def test_minimal_summary_validates() -> None:
    s = CampaignRunSummary.model_validate(_minimal_summary())
    assert s.contract_version == PIPELINE_RUN_VERSION
    assert s.overall_state is CreativeAssetState.DRAFT


def test_summary_round_trip_json() -> None:
    s = CampaignRunSummary.model_validate(_minimal_summary())
    reloaded = CampaignRunSummary.from_json(s.to_json())
    assert reloaded.model_dump() == s.model_dump()


def test_summary_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignRunSummary.model_validate(
            _minimal_summary(created_at="2026-05-30T12:00:00")
        )


def test_summary_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignRunSummary.model_validate(_minimal_summary(client_slug="Bad Slug"))


def test_summary_version_pinned() -> None:
    with pytest.raises(ValidationError):
        CampaignRunSummary.model_validate(
            _minimal_summary(contract_version="pipeline-run.v2")
        )


def test_summary_extra_field_rejected() -> None:
    data = _minimal_summary()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        CampaignRunSummary.model_validate(data)


def test_summary_duration_seconds() -> None:
    s = CampaignRunSummary.model_validate(
        _minimal_summary(
            started_at="2026-05-30T12:00:00+00:00",
            finished_at="2026-05-30T12:00:30+00:00",
        )
    )
    assert s.duration_seconds == 30.0


def test_count_by_outcome() -> None:
    stages = [
        StageResult(
            stage_id=StageId.INTAKE,
            outcome=StageOutcome.SUCCEEDED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
        StageResult(
            stage_id=StageId.APPROVAL,
            outcome=StageOutcome.BLOCKED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
        StageResult(
            stage_id=StageId.CREATIVE,
            outcome=StageOutcome.SKIPPED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
    ]
    s = CampaignRunSummary.model_validate(_minimal_summary(stages=stages))
    counts = s.count_by_outcome()
    assert counts["succeeded"] == 1
    assert counts["blocked"] == 1
    assert counts["skipped"] == 1
    assert counts["failed"] == 0


def test_get_stage() -> None:
    stages = [
        StageResult(
            stage_id=StageId.INTAKE,
            outcome=StageOutcome.SUCCEEDED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
    ]
    s = CampaignRunSummary.model_validate(_minimal_summary(stages=stages))
    assert s.get_stage(StageId.INTAKE) is not None
    assert s.get_stage(StageId.VISUAL) is None


def test_is_complete_true_when_only_succeeded_or_skipped() -> None:
    stages = [
        StageResult(
            stage_id=StageId.INTAKE,
            outcome=StageOutcome.SUCCEEDED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
        StageResult(
            stage_id=StageId.STRATEGY,
            outcome=StageOutcome.SKIPPED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
    ]
    s = CampaignRunSummary.model_validate(_minimal_summary(stages=stages))
    assert s.is_complete is True


def test_is_complete_false_with_failed() -> None:
    stages = [
        StageResult(
            stage_id=StageId.INTAKE,
            outcome=StageOutcome.FAILED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
    ]
    s = CampaignRunSummary.model_validate(_minimal_summary(stages=stages))
    assert s.is_complete is False


def test_is_complete_false_with_blocked() -> None:
    stages = [
        StageResult(
            stage_id=StageId.APPROVAL,
            outcome=StageOutcome.BLOCKED,
            started_at=_now(),
            finished_at=_now(),
        ).model_dump(mode="json"),
    ]
    s = CampaignRunSummary.model_validate(_minimal_summary(stages=stages))
    assert s.is_complete is False


# ---------- StageResult ----------

def test_stage_result_requires_tz() -> None:
    with pytest.raises(ValidationError):
        StageResult(
            stage_id=StageId.INTAKE,
            outcome=StageOutcome.SUCCEEDED,
            started_at=datetime(2026, 5, 30, 12, 0),
            finished_at=_now(),
        )


def test_stage_result_round_trip() -> None:
    s = StageResult(
        stage_id=StageId.INTAKE,
        outcome=StageOutcome.SUCCEEDED,
        started_at=_now(),
        finished_at=_now(),
        artifact_refs=["a.md"],
        memory_refs=["k/current"],
    )
    reloaded = StageResult.from_json(s.to_json())
    assert reloaded.model_dump() == s.model_dump()
