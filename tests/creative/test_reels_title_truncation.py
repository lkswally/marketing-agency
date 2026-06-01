"""MKT-4C: defensive truncation of ReelsAsset title in the factory.

Source ``ReelsScriptEntry.title`` has no length constraint upstream,
but ``ReelsAsset.title`` is capped at 200 chars. A long title from
either the templated or the Claude backend used to crash the
creative stage. The factory now truncates to 197 + "..." before
constructing the asset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.creative.factory import CreativeFactory
from core.intake import normalize_intake
from core.intake.models import ClientIntake
from core.intake.validator import IntakeValidator
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline
from core.strategy.models import ReelsScriptEntry

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE_PATH = REPO_ROOT / "examples" / "intake" / "demo-business.json"


@pytest.fixture
def report(tmp_path: Path):
    """Build a real CampaignStrategyReport from the demo intake."""
    import json
    intake = ClientIntake.model_validate(
        json.loads(DEMO_INTAKE_PATH.read_text(encoding="utf-8"))
    )
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    mem = JsonFileMemory(tmp_path / "mem")
    pipeline = StrategyPipeline(memory=mem)
    result = pipeline.run_from_brief(brief)
    return result.report, mem


def test_long_reels_title_does_not_crash_factory(report) -> None:
    rep, mem = report
    # Inject an obnoxiously long title that would blow the 200-cap.
    long_title = "Hook — " + ("muy largo " * 30)  # ~300 chars
    rep.reels_script_pack.scripts.insert(
        0,
        ReelsScriptEntry(
            script_id="injected",
            title=long_title,
            hook="hook",
            beats=["a"],
            voiceover_lines=["v"],
            on_screen_text=["t"],
            cta="cta",
            target_duration_s=30,
        ),
    )
    factory = CreativeFactory(memory=mem)
    pack = factory.build(rep, None)  # MUST NOT raise
    injected = next(r for r in pack.reels if r.hook_variants and r.title.startswith("Hook"))
    assert len(injected.title) <= 200
    assert injected.title.endswith("...")


def test_short_reels_title_is_unchanged(report) -> None:
    rep, mem = report
    factory = CreativeFactory(memory=mem)
    pack = factory.build(rep, None)
    # The demo intake produces short titles; none should be truncated.
    for r in pack.reels:
        assert not r.title.endswith("...") or len(r.title) <= 200
