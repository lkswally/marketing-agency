"""CLI tests for `mkt portal` (MKT-9A)."""

from __future__ import annotations

import io

from cli.main import main


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def test_portal_prints_install_hint_when_streamlit_missing(monkeypatch) -> None:
    """When Streamlit is not installed, the wrapper exits 2 and
    prints the install command. We simulate the missing dependency
    by monkey-patching ``importlib.util.find_spec``."""
    import importlib.util

    original = importlib.util.find_spec

    def fake(name, *a, **kw):
        if name == "streamlit":
            return None
        return original(name, *a, **kw)

    monkeypatch.setattr(importlib.util, "find_spec", fake)
    code, stdout = _run(["portal"])
    assert code == 2
    assert "streamlit" in stdout.lower()
    assert "[portal]" in stdout


def test_portal_does_not_spawn_when_streamlit_missing(monkeypatch) -> None:
    """Pin: when Streamlit is missing, the wrapper must not call
    subprocess. We patch subprocess.call to detect any call and
    fail the test if it happens."""
    import importlib.util
    import subprocess

    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name, *a, **kw: None if name == "streamlit" else
        importlib.util.find_spec(name, *a, **kw),
    )
    called = {"count": 0}

    def fake_call(*a, **kw):
        called["count"] += 1
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    code, _ = _run(["portal"])
    assert code == 2
    assert called["count"] == 0


def test_portal_passes_paths_when_streamlit_present(monkeypatch, tmp_path) -> None:
    """When Streamlit is reported as installed, the wrapper composes
    the expected `streamlit run` command with --root + --outputs-dir
    after the `--` separator. We patch subprocess.call to capture
    the command and return 0."""
    import importlib.util
    import subprocess

    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name, *a, **kw: object(),  # always "found"
    )

    captured: dict = {}

    def fake_call(cmd, *a, **kw):
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    code, _ = _run([
        "portal",
        "--root", str(tmp_path / "data"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    cmd = captured["cmd"]
    assert "streamlit" in cmd
    assert "run" in cmd
    assert "--" in cmd
    sep = cmd.index("--")
    tail = cmd[sep + 1:]
    assert "--root" in tail and str(tmp_path / "data") in tail
    assert "--outputs-dir" in tail and str(tmp_path / "out") in tail


def test_portal_help_does_not_crash() -> None:
    """argparse should accept `mkt portal --help` cleanly."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        _run(["portal", "--help"])
    # argparse uses exit 0 for --help.
    assert exc.value.code == 0
