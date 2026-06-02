"""CLI tests for `mkt notion-sync`.

Cover the safety gates, env-var fallbacks, and the mocked write
path. Zero real Notion calls.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _prime(tmp_path: Path) -> str:
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    slug = json.loads(text)["client_slug"]
    assert _run(
        [
            "build-tasks",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )[0] == 0
    assert _run(
        [
            "notion-plan",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )[0] == 0
    return slug


# ---------- safety gate ----------

def test_write_without_confirm_exits_3(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, text = _run(
        [
            "notion-sync",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
            "--write",
        ]
    )
    assert code == 3
    assert "--confirm" in text


def test_missing_plan_returns_exit_2(tmp_path: Path) -> None:
    code, text = _run(
        [
            "notion-sync",
            "--client", "ghost",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no NotionSyncPlan" in text


# ---------- dry-run default ----------

def test_default_is_dry_run(tmp_path: Path, monkeypatch) -> None:
    """No --write flag → dry-run. Even with token env vars set, the
    executor must not call Notion."""
    monkeypatch.setenv("NOTION_TOKEN", "ntn-fake")
    monkeypatch.setenv("NOTION_TASKS_DATABASE_ID", "db-fake")
    slug = _prime(tmp_path)
    code, text = _run(
        [
            "notion-sync",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["mode"] == "dry_run"
    assert payload["write_attempted"] is False


def test_explicit_dry_run_flag(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    code, text = _run(
        [
            "notion-sync",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
            "--dry-run",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["mode"] == "dry_run"
    assert payload["write_attempted"] is False


# ---------- fallbacks: missing creds ----------

def test_write_without_token_falls_back(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.setenv("NOTION_TASKS_DATABASE_ID", "db-x")
    slug = _prime(tmp_path)
    code = main(
        [
            "notion-sync",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
            "--write", "--confirm",
        ],
        out=__import__("sys").stdout,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "NOTION_TOKEN" in captured.err


def test_write_without_database_id_falls_back(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "ntn-fake")
    monkeypatch.delenv("NOTION_TASKS_DATABASE_ID", raising=False)
    slug = _prime(tmp_path)
    code = main(
        [
            "notion-sync",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out" / slug),
            "--write", "--confirm",
        ],
        out=__import__("sys").stdout,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "NOTION_TASKS_DATABASE_ID" in captured.err


# ---------- mocked write path ----------

def test_write_with_mocked_client_creates_pages(
    tmp_path: Path, monkeypatch
) -> None:
    """Inject a mocked Notion client through NotionClientWriter.__init__
    so the executor really walks the write path without hitting the
    network."""
    monkeypatch.setenv("NOTION_TOKEN", "ntn-fake")
    monkeypatch.setenv("NOTION_TASKS_DATABASE_ID", "db-fake")
    slug = _prime(tmp_path)

    from core.notion_sync import writer as writer_mod

    mock_client = MagicMock()

    def _create(**kwargs):
        r = MagicMock()
        r.id = f"page-mock-{len(mock_client.pages.create.mock_calls)}"
        return r

    mock_client.pages.create.side_effect = _create

    original_init = writer_mod.NotionClientWriter.__init__

    def patched_init(self, *args, **kwargs):
        if "client" not in kwargs:
            kwargs["client"] = mock_client
        original_init(self, *args, **kwargs)

    with patch.object(writer_mod.NotionClientWriter, "__init__", patched_init):
        code, text = _run(
            [
                "notion-sync",
                "--client", slug,
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out" / slug),
                "--write", "--confirm",
            ]
        )
    assert code == 0
    payload = json.loads(text)
    assert payload["mode"] == "write"
    assert payload["write_attempted"] is True
    assert payload["stats"]["created"] > 0
    # The mocked SDK was called once per created page.
    assert mock_client.pages.create.call_count >= payload["stats"]["created"]


# ---------- output files ----------

def test_writes_md_and_json_files(tmp_path: Path) -> None:
    slug = _prime(tmp_path)
    out_dir = tmp_path / "out" / slug
    _, text = _run(
        [
            "notion-sync",
            "--client", slug,
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(out_dir),
        ]
    )
    payload = json.loads(text)
    md = Path(payload["markdown_path"])
    js = Path(payload["json_path"])
    assert md.exists()
    assert js.exists()
    md_text = md.read_text(encoding="utf-8")
    assert "DRY-RUN" in md_text


# ---------- safety: dry-run never imports notion_client at execution time ----------

def test_dry_run_does_not_require_notion_sdk(tmp_path: Path, monkeypatch) -> None:
    """Stub notion_client to None in sys.modules; the dry-run path
    must run cleanly."""
    import sys
    saved = sys.modules.get("notion_client")
    sys.modules["notion_client"] = None  # type: ignore[assignment]
    try:
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        slug = _prime(tmp_path)
        code, text = _run(
            [
                "notion-sync",
                "--client", slug,
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out" / slug),
            ]
        )
        assert code == 0
        payload = json.loads(text)
        assert payload["mode"] == "dry_run"
    finally:
        if saved is not None:
            sys.modules["notion_client"] = saved
        else:
            sys.modules.pop("notion_client", None)
