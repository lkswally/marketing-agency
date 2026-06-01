"""CLI tests for `--backend claude` with the Anthropic SDK invoker (MKT-4B).

ALL tests mock the SDK boundary. No real Anthropic call is ever made.

Three scenarios are covered:

- ``ANTHROPIC_API_KEY`` absent → RefusingClaudeInvoker → fallback x6.
- Key present, SDK raises an error on every call → fallback x6 with
  the SDK error class name surfaced in the notes + audit.
- Key present, SDK returns valid JSON for each of the 6 methods →
  ``backend_effective="claude"``, zero fallbacks, six invocation
  records in the summary.

The CLI wires :class:`AnthropicSDKInvoker` with the real SDK client
only when the env var is set. We intercept that wiring by
monkey-patching :class:`AnthropicSDKInvoker.__init__` to inject our
mocked ``client`` kwarg.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.main import main
from core.strategy.backends.invokers import anthropic_sdk as sdk_module

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


# ---------- helpers ----------

def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _ok_response(text: str, *, request_id: str = "req_test", model: str = "mock-model",
                 in_tok: int = 80, out_tok: int = 40) -> MagicMock:
    r = MagicMock()
    r.id = request_id
    r.model = model
    r.usage = MagicMock(input_tokens=in_tok, output_tokens=out_tok)
    block = MagicMock(text=text)
    r.content = [block]
    return r


def _valid_json_for(method: str) -> str:
    """Minimal valid JSON the Pydantic models accept, per method."""
    if method == "value_proposition":
        return json.dumps({
            "headline": "Activá la confianza desde el primer click",
            "category": "saas",
            "target_audience_label": "PyMEs",
            "differentiators": ["onboarding guiado"],
            "proof_points": ["48h de implementación"],
            "primary_benefit": "menos fricción",
        })
    if method == "campaign_strategy":
        return json.dumps({
            "objective": "Lanzar la propuesta a PyMEs en LATAM",
            "duration_weeks": 6,
            "primary_kpi": "MQLs calificados",
            "secondary_kpis": ["CTR", "demo bookings"],
            "funnel_focus": "consideration",
            "big_idea": "Confianza activable en 48h",
            "narrative_arc": ["problema", "promesa", "prueba"],
        })
    if method == "creative_brief_pack":
        return json.dumps({
            "briefs": [
                {
                    "brief_id": "b1",
                    "title": "Hero",
                    "piece_type": "instagram_post",
                    "aspect_ratio": "1:1",
                    "visual_concept": "minimal con foco en producto",
                    "copy_overlay": ["activá la confianza"],
                    "prompt_for_image_model": "minimal product hero",
                }
            ],
            "overall_visual_direction": "minimal",
        })
    if method == "social_post_drafts":
        return json.dumps({
            "items": [
                {
                    "post_id": "p1",
                    "channel": "instagram",
                    "hook": "Lo activás en 48h",
                    "body": "Onboarding guiado, sin curva.",
                    "cta": "Probalo gratis",
                    "hashtags": ["#pymes"],
                }
            ]
        })
    if method == "email_sequence":
        return json.dumps({
            "sequence_name": "lanzamiento",
            "goal": "convertir trials",
            "audience_label": "PyMEs",
            "emails": [
                {
                    "email_id": "e1",
                    "step": 1,
                    "subject": "Hola, bienvenida",
                    "preview_text": "Activá tu cuenta",
                    "body": "Body del email.",
                    "cta": "Empezar",
                    "send_after_days": 0,
                }
            ],
        })
    if method == "reels_script_pack":
        return json.dumps({
            "scripts": [
                {
                    "script_id": "s1",
                    "title": "48h",
                    "hook": "Lo activás en 48h",
                    "beats": ["problema", "solución"],
                    "voiceover_lines": ["bienvenida"],
                    "on_screen_text": ["48h"],
                    "cta": "probá gratis",
                    "target_duration_s": 30,
                }
            ],
            "overall_tone": "directo",
        })
    raise AssertionError(f"unknown method: {method}")


class _FakeAnthropicClient:
    """Mock client that returns per-method valid JSON."""

    def __init__(self, raises_for: set[str] | None = None,
                 exc_class: type[BaseException] = RuntimeError) -> None:
        self.messages = MagicMock()
        self.messages.create.side_effect = self._create
        self.raises_for = raises_for or set()
        self.exc_class = exc_class
        self._method_order = [
            "value_proposition",
            "campaign_strategy",
            "creative_brief_pack",
            "social_post_drafts",
            "email_sequence",
            "reels_script_pack",
        ]
        self._next_index = 0

    def _create(self, **kwargs):
        # The ClaudeStrategyBackend builds prompts with the method name in
        # the prompt body; we infer the method from the kwargs body so we
        # do not depend on call order.
        body = kwargs["messages"][0]["content"]
        method = self._infer_method(body)
        if method in self.raises_for:
            raise self.exc_class(f"{method} forced failure")
        return _ok_response(_valid_json_for(method), request_id=f"req_{method}")

    @staticmethod
    def _infer_method(prompt: str) -> str:
        # Pick the first method-token that appears in the prompt body. The
        # prompt builders mention the target schema name verbatim, and they
        # are distinctive enough to disambiguate.
        markers = {
            "ValueProposition": "value_proposition",
            "CampaignStrategy": "campaign_strategy",
            "CreativeBriefPack": "creative_brief_pack",
            "SocialPostDraft": "social_post_drafts",
            "EmailSequenceDraft": "email_sequence",
            "ReelsScriptPack": "reels_script_pack",
        }
        for marker, method in markers.items():
            if marker in prompt:
                return method
        raise AssertionError("could not infer method from prompt")


@pytest.fixture
def patched_invoker_factory():
    """Patch :class:`AnthropicSDKInvoker.__init__` to inject a fake client.

    The CLI calls ``AnthropicSDKInvoker(api_key=..., model=...)`` without
    a ``client`` kwarg. We wrap the real ``__init__`` to add our fake
    client transparently. The actual ``anthropic`` SDK is never imported.
    """
    original_init = sdk_module.AnthropicSDKInvoker.__init__
    fake_client = _FakeAnthropicClient()

    def patched_init(self, *args, **kwargs):
        if "client" not in kwargs:
            kwargs["client"] = fake_client
        original_init(self, *args, **kwargs)

    with patch.object(sdk_module.AnthropicSDKInvoker, "__init__", patched_init):
        yield fake_client


@pytest.fixture
def patched_invoker_factory_raising():
    original_init = sdk_module.AnthropicSDKInvoker.__init__
    # All 6 methods raise an SDK-like error.
    all_methods = {
        "value_proposition", "campaign_strategy", "creative_brief_pack",
        "social_post_drafts", "email_sequence", "reels_script_pack",
    }
    # Use a dynamic class named like an SDK error.
    auth_error_cls = type("AuthenticationError", (Exception,), {})
    fake_client = _FakeAnthropicClient(
        raises_for=all_methods, exc_class=auth_error_cls
    )

    def patched_init(self, *args, **kwargs):
        if "client" not in kwargs:
            kwargs["client"] = fake_client
        original_init(self, *args, **kwargs)

    with patch.object(sdk_module.AnthropicSDKInvoker, "__init__", patched_init):
        yield fake_client


# ---------- tests: env var absent ----------

def test_backend_claude_without_env_var_falls_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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
    assert payload["backend_effective"] == "templated"
    assert payload["backend_fallback_count"] == 6


def test_backend_claude_without_env_var_warns_on_stderr(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code = main(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--backend", "claude",
        ],
        out=sys.stdout,
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY" in captured.err
    assert "WARNING" in captured.err


# ---------- tests: env var present, SDK errors out ----------

def test_backend_claude_with_sdk_errors_falls_back(
    tmp_path: Path, monkeypatch, patched_invoker_factory_raising
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-not-real")
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
    assert payload["backend_effective"] == "templated"
    assert payload["backend_fallback_count"] == 6
    notes = payload["backend_fallback_notes"]
    assert len(notes) == 6
    assert all("AuthenticationError" in n for n in notes)


# ---------- tests: env var present, SDK happy path ----------

def test_backend_claude_with_valid_responses_uses_claude(
    tmp_path: Path, monkeypatch, patched_invoker_factory
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-not-real")
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
    assert payload["backend_effective"] == "claude"
    assert payload["backend_fallback_count"] == 0


def test_backend_claude_records_invocations_in_summary(
    tmp_path: Path, monkeypatch, patched_invoker_factory
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-not-real")
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
    outputs_dir = Path(payload["outputs_dir"])
    # The summary on disk has the full invocation list.
    summary_json = json.loads(
        (outputs_dir / "campaign-final-summary.json").read_text(encoding="utf-8")
    )
    invocations = summary_json["claude_invocations"]
    assert len(invocations) == 6
    methods = {inv["method"] for inv in invocations}
    assert methods == {
        "value_proposition", "campaign_strategy", "creative_brief_pack",
        "social_post_drafts", "email_sequence", "reels_script_pack",
    }
    for inv in invocations:
        assert inv["ok"] is True
        assert inv["request_id"]
        assert inv["input_tokens"] == 80
        assert inv["output_tokens"] == 40


def test_claude_model_flag_overrides_env_and_default(
    tmp_path: Path, monkeypatch, patched_invoker_factory
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-not-real")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-from-env-NOT-USED")
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--backend", "claude",
            "--claude-model", "claude-from-flag",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    outputs_dir = Path(payload["outputs_dir"])
    summary_json = json.loads(
        (outputs_dir / "campaign-final-summary.json").read_text(encoding="utf-8")
    )
    for inv in summary_json["claude_invocations"]:
        assert inv["model"] == "claude-from-flag"


# ---------- tests: env var present but SDK not installed ----------

def test_backend_claude_with_missing_sdk_falls_back(
    tmp_path: Path, monkeypatch
) -> None:
    """If the optional `anthropic` package is not installed and the
    invoker tries to lazy-import it, NoCredentialsError fires and the
    CLI falls back to RefusingClaudeInvoker → templated."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    # Force the lazy import inside AnthropicSDKInvoker.__init__ to fail.
    import sys as _sys
    saved = _sys.modules.get("anthropic", None)
    _sys.modules["anthropic"] = None  # type: ignore[assignment]
    try:
        code, text = _run(
            [
                "run-campaign",
                "--intake", str(DEMO_INTAKE),
                "--root", str(tmp_path / "mem"),
                "--outputs-dir", str(tmp_path / "out"),
                "--backend", "claude",
            ]
        )
    finally:
        if saved is not None:
            _sys.modules["anthropic"] = saved
        else:
            _sys.modules.pop("anthropic", None)
    assert code == 0
    payload = json.loads(text)
    assert payload["backend_requested"] == "claude"
    assert payload["backend_effective"] == "templated"
    assert payload["backend_fallback_count"] == 6


# ---------- tests: env var NOT consulted when --backend templated ----------

def test_env_var_ignored_when_backend_templated(
    tmp_path: Path, monkeypatch
) -> None:
    """Even with ANTHROPIC_API_KEY set, no claude invoker is wired
    when --backend templated (the default)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
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
