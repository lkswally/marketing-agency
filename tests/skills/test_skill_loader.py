"""Skill loader tests — must successfully parse all real skill specs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.skills import SkillLoadError, load_all_skills, load_skill

REPO_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


def test_load_all_real_skills() -> None:
    specs = load_all_skills(REPO_SKILLS_DIR)
    assert len(specs) == 24
    ids = {s.skill_id for s in specs}
    expected = {
        "brand-voice-extractor",
        "icp-definition",
        "keyword-research",
        "negative-keywords",
        "hashtag-research",
        "competitor-benchmark",
        "channel-recommendation",
        "paid-ads-plan",
        "seo-content-plan",
        "landing-copy",
        "email-sequence-draft",
        "social-post-draft",
        "creative-brief",
        "reels-script",
        "claim-validator",
        "approval-packager",
        "optimization-recommendation",
        # MKT-10X
        "competitor-intelligence",
        "trend-detector",
        "content-gap-finder",
        "creative-fatigue-scorer",
        "budget-pacer",
        "weekly-executive-report",
        "utm-builder",
    }
    assert expected.issubset(ids)


def test_all_real_skills_are_spec_only() -> None:
    for spec in load_all_skills(REPO_SKILLS_DIR):
        assert spec.status == "spec_only", spec.skill_id


def test_no_real_skill_has_external_dependencies() -> None:
    # MKT-1E rule: no skill ships with deps in v1.
    for spec in load_all_skills(REPO_SKILLS_DIR):
        assert spec.external_dependencies == [], spec.skill_id


def test_load_skill_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError):
        load_skill(tmp_path / "nope.md")


def test_load_skill_no_frontmatter_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("body only\n", encoding="utf-8")
    with pytest.raises(SkillLoadError):
        load_skill(p)


def test_load_skill_invalid_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("---\nbad:::: yaml: [\n---\n", encoding="utf-8")
    with pytest.raises(SkillLoadError):
        load_skill(p)


def test_load_skill_validation_error_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nskill_id: BAD\nversion: 1\nspec_version: skill-spec.v1\nstatus: spec_only\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillLoadError):
        load_skill(p)


def test_load_all_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert load_all_skills(tmp_path) == []
