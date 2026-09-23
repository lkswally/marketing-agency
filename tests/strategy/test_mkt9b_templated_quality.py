"""MKT-9B regression tests for templated backend quality fixes.

A real-business alpha pilot (anonymized here as the LEGALCASE DEMO
synthetic fixture) surfaced:

- Every channel rationale read identically ("Match con audiencia
  (X); rol esperado: Y."). Now each channel has a role-specific
  reason + objective tie-in.
- The executive summary headline did not use any of the client's
  preferred words. Now it weaves one in.
- The competitor benchmark mentioned a count but not the names.
  Now it lists the top 3 by name.
- ``forbidden_words`` from the intake did not surface anywhere
  in the strategy report. Now the business diagnosis records
  them as a challenge so the approval reviewer sees them early.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGALCASE_DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "legalcase-demo.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _build_legalcase_demo(tmp_path: Path) -> dict:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(LEGALCASE_DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    raw = (
        tmp_path / "mem" / "legalcase-demo" / "campaign_strategy_report"
        / "current.json"
    ).read_text(encoding="utf-8")
    return json.loads(raw)


def test_executive_summary_uses_a_preferred_word(tmp_path: Path) -> None:
    report = _build_legalcase_demo(tmp_path)
    headline = report["executive_summary"]["headline"]
    intake = json.loads(LEGALCASE_DEMO_INTAKE.read_text(encoding="utf-8"))
    preferred = [w.lower() for w in intake["preferred_words"]]
    # At least one preferred word from the intake must appear in
    # the executive headline.
    assert any(w in headline.lower() for w in preferred), (
        f"Headline {headline!r} did not weave in any preferred word."
    )


def test_channel_rationales_are_not_all_identical(tmp_path: Path) -> None:
    """Pin: no two channels share the EXACT rationale text — the
    previous boilerplate emitted the same string for every
    channel."""
    report = _build_legalcase_demo(tmp_path)
    rationales = [
        c["rationale"]
        for c in report["channel_recommendation"]["channels"]
    ]
    assert len(rationales) >= 2
    assert len(set(rationales)) == len(rationales), (
        "Channel rationales repeat — they should be channel-specific."
    )


def test_channel_overall_rationale_mentions_top_channels(tmp_path: Path) -> None:
    report = _build_legalcase_demo(tmp_path)
    overall = report["channel_recommendation"]["rationale_overall"]
    channels = [
        c["channel_type"]
        for c in report["channel_recommendation"]["channels"][:2]
    ]
    assert channels, "Expected at least one channel"
    # The overall rationale must mention at least the top channel.
    assert channels[0] in overall, (
        f"Overall rationale does not mention top channel {channels[0]!r}: "
        f"{overall!r}"
    )


def test_competitor_takeaway_lists_competitor_names(tmp_path: Path) -> None:
    report = _build_legalcase_demo(tmp_path)
    takeaway = report["competitor_benchmark"]["overall_takeaway"]
    intake = json.loads(LEGALCASE_DEMO_INTAKE.read_text(encoding="utf-8"))
    listed = [c["name"] for c in intake["known_competitors"][:3]]
    # At least one of the top-3 competitor names is rendered.
    assert any(name in takeaway for name in listed), (
        f"Takeaway {takeaway!r} mentions none of: {listed}"
    )


def test_diagnosis_surfaces_forbidden_claims(tmp_path: Path) -> None:
    report = _build_legalcase_demo(tmp_path)
    challenges = report["diagnosis"]["challenges"]
    intake = json.loads(LEGALCASE_DEMO_INTAKE.read_text(encoding="utf-8"))
    forbidden = intake["forbidden_words"]
    blob = " | ".join(challenges)
    # At least one forbidden word is echoed back so the reviewer
    # can grep for it.
    assert any(w in blob for w in forbidden), (
        "Diagnosis did not record the forbidden-words guard."
    )


def test_diagnosis_lists_competitor_names(tmp_path: Path) -> None:
    report = _build_legalcase_demo(tmp_path)
    strengths = report["diagnosis"]["strengths"]
    intake = json.loads(LEGALCASE_DEMO_INTAKE.read_text(encoding="utf-8"))
    listed = [c["name"] for c in intake["known_competitors"][:3]]
    blob = " | ".join(strengths)
    assert any(name in blob for name in listed), (
        f"Diagnosis strengths {strengths!r} mention none of: {listed}"
    )
