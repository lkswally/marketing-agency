"""ClaudeStrategyBackend — LLM-backed content with deterministic fallback.

For each method:

1. Build a prompt with :mod:`.prompts`.
2. Call ``invoker.complete(...)``.
3. Parse the response as JSON.
4. Validate against the target Pydantic model.
5. On any failure (invoker raises, JSON parse error, Pydantic
   validation error) → record a :class:`BackendFallbackEvent` and
   delegate to the fallback backend.

The fallback backend defaults to :class:`TemplatedStrategyBackend`.
Callers can inject a different fallback for testing but it MUST be
a :class:`StrategyBackend`.

No network. No filesystem writes outside what the fallback does. No
credentials. The invoker is the only thing that could possibly do
those — and in MKT-4A every shipped invoker is local-only
(scripted or refusing).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..models import (
    CampaignStrategy,
    ChannelRecommendation,
    CreativeBriefPack,
    EmailSequenceDraft,
    KeywordPlan,
    ReelsScriptPack,
    SocialPostDraft,
    StrategyInputBrief,
    TargetAudience,
    ValueProposition,
)
from . import prompts
from .base import (
    BackendFallbackEvent,
    BackendKind,
    StrategyBackend,
)
from .invocation_log import ClaudeInvocationRecord
from .invoker import (
    ClaudeInvocationContext,
    ClaudeInvoker,
    ClaudeInvokerError,
)
from .templated import TemplatedStrategyBackend


class ClaudeOutputInvalid(RuntimeError):  # noqa: N818
    """Internal sentinel. The backend catches this and falls back —
    callers never see it."""


_MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB sanity ceiling for any LLM response.


class ClaudeStrategyBackend(StrategyBackend):
    """LLM-backed content with automatic fallback to a templated backend."""

    kind = BackendKind.CLAUDE

    def __init__(
        self,
        invoker: ClaudeInvoker,
        *,
        fallback: StrategyBackend | None = None,
        client_slug: str | None = None,
    ) -> None:
        self._invoker = invoker
        self._fallback = fallback or TemplatedStrategyBackend()
        self._client_slug = client_slug or "unknown"
        self._fallback_events: list[BackendFallbackEvent] = []
        self._invocation_records: list[ClaudeInvocationRecord] = []

    # ---------- introspection ----------

    def drain_fallback_events(self) -> list[BackendFallbackEvent]:
        events = list(self._fallback_events)
        self._fallback_events.clear()
        return events

    def drain_invocation_records(self) -> list[ClaudeInvocationRecord]:
        """Return and clear the per-call invocation records collected
        from the invoker's ``record_sink``. The templated backend
        never produces these; the SDK invoker produces one per call
        (success or failure)."""
        records = list(self._invocation_records)
        self._invocation_records.clear()
        return records

    def set_client_slug(self, slug: str) -> None:
        """Used by the W7 layer to propagate the tenant slug before a run."""
        self._client_slug = slug

    # ---------- StrategyBackend implementations ----------

    def value_proposition(
        self,
        brief: StrategyInputBrief,
        audience: TargetAudience,
    ) -> ValueProposition:
        prompt = prompts.value_proposition_prompt(brief, audience)
        return self._invoke_or_fallback(
            method="value_proposition",
            prompt=prompt,
            model_cls=ValueProposition,
            fallback_call=lambda: self._fallback.value_proposition(brief, audience),
        )

    def campaign_strategy(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
    ) -> CampaignStrategy:
        prompt = prompts.campaign_strategy_prompt(brief, value_prop)
        return self._invoke_or_fallback(
            method="campaign_strategy",
            prompt=prompt,
            model_cls=CampaignStrategy,
            fallback_call=lambda: self._fallback.campaign_strategy(brief, value_prop),
        )

    def creative_brief_pack(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> CreativeBriefPack:
        prompt = prompts.creative_brief_pack_prompt(brief, value_prop, audience)
        return self._invoke_or_fallback(
            method="creative_brief_pack",
            prompt=prompt,
            model_cls=CreativeBriefPack,
            fallback_call=lambda: self._fallback.creative_brief_pack(
                brief, value_prop, audience
            ),
        )

    def social_post_drafts(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        channels: ChannelRecommendation,
        keyword_plan: KeywordPlan,
    ) -> list[SocialPostDraft]:
        prompt = prompts.social_post_drafts_prompt(
            brief, value_prop, channels, keyword_plan
        )

        def _fallback_call() -> list[SocialPostDraft]:
            return self._fallback.social_post_drafts(
                brief, value_prop, channels, keyword_plan
            )

        try:
            raw = self._call_invoker("social_post_drafts", prompt)
            parsed = self._parse_json(raw)
            if not isinstance(parsed, dict) or "items" not in parsed:
                raise ClaudeOutputInvalid("missing top-level 'items' key")
            items = parsed["items"]
            if not isinstance(items, list):
                raise ClaudeOutputInvalid("'items' is not a list")
            return [SocialPostDraft.model_validate(item) for item in items]
        except (ClaudeInvokerError, ClaudeOutputInvalid, ValidationError) as e:
            self._record_fallback("social_post_drafts", e)
            return _fallback_call()

    def email_sequence(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> EmailSequenceDraft:
        prompt = prompts.email_sequence_prompt(brief, value_prop, audience)
        return self._invoke_or_fallback(
            method="email_sequence",
            prompt=prompt,
            model_cls=EmailSequenceDraft,
            fallback_call=lambda: self._fallback.email_sequence(
                brief, value_prop, audience
            ),
        )

    def reels_script_pack(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> ReelsScriptPack:
        prompt = prompts.reels_script_pack_prompt(brief, value_prop, audience)
        return self._invoke_or_fallback(
            method="reels_script_pack",
            prompt=prompt,
            model_cls=ReelsScriptPack,
            fallback_call=lambda: self._fallback.reels_script_pack(
                brief, value_prop, audience
            ),
        )

    # ---------- internals ----------

    def _invoke_or_fallback(
        self,
        *,
        method: str,
        prompt: str,
        model_cls,
        fallback_call,
    ):
        try:
            raw = self._call_invoker(method, prompt)
            parsed = self._parse_json(raw)
            return model_cls.model_validate(parsed)
        except (ClaudeInvokerError, ClaudeOutputInvalid, ValidationError) as e:
            self._record_fallback(method, e)
            return fallback_call()

    def _call_invoker(self, method: str, prompt: str) -> str:
        # Fresh sink per call. The invoker appends one record (success or
        # failure). We drain unconditionally — the ``finally`` block makes
        # sure the record is collected even when the invoker raises.
        sink: list[ClaudeInvocationRecord] = []
        context = ClaudeInvocationContext(
            method=method,
            client_slug=self._client_slug,
            record_sink=sink,
        )
        try:
            raw = self._invoker.complete(
                prompt,
                system=prompts.SYSTEM_PROMPT,
                context=context,
            )
        finally:
            if sink:
                self._invocation_records.extend(sink)
        if not isinstance(raw, str):
            raise ClaudeOutputInvalid(
                f"invoker returned {type(raw).__name__}, expected str"
            )
        if len(raw.encode("utf-8", errors="replace")) > _MAX_OUTPUT_BYTES:
            raise ClaudeOutputInvalid(
                f"invoker returned >{_MAX_OUTPUT_BYTES} bytes (suspicious)"
            )
        return raw

    @staticmethod
    def _parse_json(raw: str) -> Any:
        # Strip optional markdown fences the model might add despite the prompt.
        stripped = raw.strip()
        if stripped.startswith("```"):
            # Remove the opening fence (```json or ```)
            stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
            # Remove trailing fence.
            if stripped.endswith("```"):
                stripped = stripped[: -len("```")]
            stripped = stripped.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ClaudeOutputInvalid(f"JSON parse failed: {e.msg}") from e

    def _record_fallback(self, method: str, exc: Exception) -> None:
        # Keep the reason short and safe — no stack traces, no secrets,
        # no raw model output.
        reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        self._fallback_events.append(
            BackendFallbackEvent(
                method=method,
                requested_backend=BackendKind.CLAUDE,
                fallback_backend=self._fallback.kind,
                reason=reason,
            )
        )


__all__ = ["ClaudeOutputInvalid", "ClaudeStrategyBackend"]
