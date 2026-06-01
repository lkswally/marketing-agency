"""CLI: `mkt run-campaign --backend templated|claude`."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def test_default_is_templated(tmp_path: Path) -> None:
    """No --backend flag → templated, no fallback, no warning anywhere."""
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["backend_requested"] == "templated"
    assert payload["backend_effective"] == "templated"
    assert payload["backend_fallback_count"] == 0
    assert payload["backend_fallback_notes"] == []


def test_explicit_templated(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--backend", "templated",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["backend_requested"] == "templated"
    assert payload["backend_effective"] == "templated"


def test_claude_backend_falls_back_with_default_invoker(tmp_path: Path) -> None:
    """`--backend claude` with no real invoker wired → fallback x6 → exit 0."""
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--backend", "claude",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["backend_requested"] == "claude"
    # All 6 creative methods fell back → effective = templated.
    assert payload["backend_effective"] == "templated"
    assert payload["backend_fallback_count"] == 6
    # Notes must mention each method, and include NoRealInvokerError as the reason.
    notes = payload["backend_fallback_notes"]
    assert len(notes) == 6
    methods = {n.split(":", 1)[0] for n in notes}
    assert methods == {
        "value_proposition",
        "campaign_strategy",
        "creative_brief_pack",
        "social_post_drafts",
        "email_sequence",
        "reels_script_pack",
    }
    assert all("NoRealInvokerError" in n for n in notes)


def test_claude_fallback_emits_stderr_warning(tmp_path: Path, capsys) -> None:
    """When CLI writes to real stdout, the warning goes to stderr."""
    argv = [
        "run-campaign",
        "--intake", str(DEMO_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
        "--backend", "claude",
    ]
    # Drive main() with the actual sys.stdout so the WARNING path uses sys.stderr.
    code = main(argv, out=sys.stdout)
    assert code == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "claude" in captured.err
    assert "fell back" in captured.err
    assert "MKT-4" in captured.err


def test_claude_fallback_visible_in_final_summary_markdown(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--backend", "claude",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    md_path = Path(payload["outputs_dir"]) / "campaign-final-summary.md"
    md = md_path.read_text(encoding="utf-8")
    assert "Strategy backend" in md
    assert "claude" in md
    # The renderer must label this as a fallback situation explicitly.
    assert "templated" in md.lower()
    assert "fallback" in md.lower() or "Fallbacks" in md
    # And it must say NO real Claude call happened.
    assert "NINGUNA" in md or "did not" in md.lower() or "NO" in md


def test_invalid_backend_value_rejected_by_argparse(tmp_path: Path) -> None:
    """argparse choices guard the flag — no silent passthrough."""
    import pytest

    out = io.StringIO()
    with pytest.raises(SystemExit) as ei:
        main(
            [
                "run-campaign",
                "--intake", str(DEMO_INTAKE),
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
                "--backend", "gpt-5",
            ],
            out=out,
        )
    assert ei.value.code == 2
