"""StrategyBackend ABC (MKT-4A).

Six methods, one per "creative" content type that the W7 strategy
engine produces. Anything structural (diagnosis, audience, competitor,
keywords, schedule, approval checklist) stays in the deterministic
templates and is not routed through this ABC — those layers do not
benefit from LLM enrichment and they need to stay reproducible byte
for byte.

The methods are:

| Method                       | Returns                  |
|------------------------------|--------------------------|
| ``value_proposition``        | :class:`ValueProposition`|
| ``campaign_strategy``        | :class:`CampaignStrategy`|
| ``creative_brief_pack``      | :class:`CreativeBriefPack` |
| ``social_post_drafts``       | ``list[SocialPostDraft]`` |
| ``email_sequence``           | :class:`EmailSequenceDraft` |
| ``reels_script_pack``        | :class:`ReelsScriptPack` |

All return values MUST be valid Pydantic instances. The Claude
backend validates the LLM output before returning; if validation
fails it falls back to the templated backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from ..models import (
    CampaignStrategy,
    CreativeBriefPack,
    EmailSequenceDraft,
    ReelsScriptPack,
    SocialPostDraft,
    StrategyInputBrief,
    TargetAudience,
    ValueProposition,
)


class BackendKind(StrEnum):
    """Identifies a backend in audit events and the run summary."""

    TEMPLATED = "templated"
    CLAUDE = "claude"


BACKEND_DEFAULT = BackendKind.TEMPLATED
"""The default backend if the operator does not pass ``--backend``."""


class StrategyBackendError(RuntimeError):  # noqa: N818
    """Base class for backend-level errors. Subclasses raise; the W7
    layer catches and records a fallback event."""


@dataclass(frozen=True)
class BackendFallbackEvent:
    """Recorded every time a :class:`StrategyBackend` method falls back.

    The W7 layer collects these and the pipeline orchestrator surfaces
    them in the audit trail, the run summary and the CLI output.
    """

    method: str
    """The StrategyBackend method that fell back, e.g. ``"value_proposition"``."""

    requested_backend: BackendKind
    """The backend the operator asked for (always ``CLAUDE`` in MKT-4A
    since the templated backend never falls back to itself)."""

    fallback_backend: BackendKind
    """The backend actually used. Always ``TEMPLATED`` in MKT-4A."""

    reason: str
    """Short human-readable reason. No stack traces, no secrets."""


class StrategyBackend(ABC):
    """Strategy content provider. Implemented by Templated and Claude."""

    #: Public identifier of this backend (used in audit + summary).
    kind: BackendKind

    @abstractmethod
    def value_proposition(
        self,
        brief: StrategyInputBrief,
        audience: TargetAudience,
    ) -> ValueProposition:
        ...

    @abstractmethod
    def campaign_strategy(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
    ) -> CampaignStrategy:
        ...

    @abstractmethod
    def creative_brief_pack(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> CreativeBriefPack:
        ...

    @abstractmethod
    def social_post_drafts(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        channels,  # ChannelRecommendation; circular-import avoidance
        keyword_plan,  # KeywordPlan; circular-import avoidance
    ) -> list[SocialPostDraft]:
        ...

    @abstractmethod
    def email_sequence(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> EmailSequenceDraft:
        ...

    @abstractmethod
    def reels_script_pack(
        self,
        brief: StrategyInputBrief,
        value_prop: ValueProposition,
        audience: TargetAudience,
    ) -> ReelsScriptPack:
        ...

    # -------- introspection --------

    def drain_fallback_events(self) -> list[BackendFallbackEvent]:
        """Return and clear any fallback events recorded since the last drain.

        The templated backend never fallbacks; returns ``[]``. The Claude
        backend records one event per method call that fell back. The W7
        layer drains after the strategy run completes.
        """
        return []


__all__ = [
    "BACKEND_DEFAULT",
    "BackendFallbackEvent",
    "BackendKind",
    "StrategyBackend",
    "StrategyBackendError",
]
