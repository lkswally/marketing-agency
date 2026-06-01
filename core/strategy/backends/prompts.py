"""Prompt templates for :class:`ClaudeStrategyBackend`.

Each method has one prompt builder. Inputs are serialised to compact
JSON via ``.model_dump(mode="json")`` — no Python ``repr`` so the
prompt is stable across runs. The system message is shared.

The prompts are deliberately strict:

- They state the contract version of the expected output schema.
- They ask for **only** a single JSON object, no prose, no markdown
  fences, no commentary.
- They forbid inventing data not derivable from the inputs.
- They forbid claims that could trigger the Claim Audit (guarantees,
  superlatives, medical/financial promises) — that audit still runs
  on the output regardless of backend.
"""

from __future__ import annotations

import json

from ..models import (
    ChannelRecommendation,
    KeywordPlan,
    StrategyInputBrief,
    TargetAudience,
    ValueProposition,
)

SYSTEM_PROMPT = (
    "You are a marketing strategist embedded in a deterministic pipeline. "
    "You produce ONE JSON object that conforms to the schema requested by "
    "the user. Rules:\n"
    "- Output ONLY the JSON object. No prose, no markdown fences, no comments.\n"
    "- Do not invent facts not derivable from the inputs.\n"
    "- Do not use guarantees, superlatives or claims that imply medical, "
    "  financial or legal outcomes — a downstream Claim Audit will block them.\n"
    "- Do not include URLs, emails, phone numbers, or PII beyond what the "
    "  inputs already contain.\n"
    "- Keep strings concise. Respect any min/max length stated in the schema.\n"
    "- Spanish (rioplatense) by default unless inputs are in another language.\n"
)


def _brief_payload(brief: StrategyInputBrief) -> dict:
    """Compact, stable dict view of the brief for prompting."""
    return brief.model_dump(mode="json")


def _audience_payload(audience: TargetAudience) -> dict:
    return audience.model_dump(mode="json")


def _value_prop_payload(value_prop: ValueProposition) -> dict:
    return value_prop.model_dump(mode="json")


# ---------- per-method prompt builders ----------


def value_proposition_prompt(
    brief: StrategyInputBrief, audience: TargetAudience
) -> str:
    return (
        "Produce a JSON object that validates against the ValueProposition "
        "schema (fields: headline str<=280, category str, "
        "target_audience_label str, differentiators list[str], "
        "proof_points list[str], primary_benefit str|null, notes str|null).\n\n"
        "INPUT brief:\n"
        f"{json.dumps(_brief_payload(brief), ensure_ascii=False, indent=2)}\n\n"
        "INPUT audience:\n"
        f"{json.dumps(_audience_payload(audience), ensure_ascii=False, indent=2)}\n\n"
        "Return only the JSON object."
    )


def campaign_strategy_prompt(
    brief: StrategyInputBrief, value_prop: ValueProposition
) -> str:
    return (
        "Produce a JSON object that validates against the CampaignStrategy "
        "schema (fields: objective str, duration_weeks int 1..52, "
        "primary_kpi str, secondary_kpis list[str], funnel_focus one of "
        "[awareness, consideration, conversion, retention, full_funnel], "
        "budget_estimate float|null>=0, budget_currency str|null, "
        "big_idea str|null, narrative_arc list[str]).\n\n"
        "INPUT brief:\n"
        f"{json.dumps(_brief_payload(brief), ensure_ascii=False, indent=2)}\n\n"
        "INPUT value_proposition:\n"
        f"{json.dumps(_value_prop_payload(value_prop), ensure_ascii=False, indent=2)}\n\n"
        "Return only the JSON object."
    )


def creative_brief_pack_prompt(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    audience: TargetAudience,
) -> str:
    return (
        "Produce a JSON object that validates against the CreativeBriefPack "
        "schema (fields: briefs list[CreativeBriefEntry], "
        "overall_visual_direction str|null, do_not_use list[str]). "
        "Each CreativeBriefEntry has fields: brief_id str, title str, "
        "piece_type str, aspect_ratio one of [1:1, 9:16, 16:9, 4:5], "
        "visual_concept str, palette_hint list[str], typography_hint str|null, "
        "copy_overlay list[str], cta str|null, accessibility_notes list[str], "
        "prompt_for_image_model str.\n\n"
        "INPUT brief:\n"
        f"{json.dumps(_brief_payload(brief), ensure_ascii=False, indent=2)}\n\n"
        "INPUT value_proposition:\n"
        f"{json.dumps(_value_prop_payload(value_prop), ensure_ascii=False, indent=2)}\n\n"
        "INPUT audience:\n"
        f"{json.dumps(_audience_payload(audience), ensure_ascii=False, indent=2)}\n\n"
        "Return only the JSON object."
    )


def social_post_drafts_prompt(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    channels: ChannelRecommendation,
    keyword_plan: KeywordPlan,
) -> str:
    return (
        "Produce a JSON object with a single top-level key 'items' whose "
        "value is a list[SocialPostDraft]. Each SocialPostDraft has fields: "
        "post_id str, channel (ChannelType enum value), hook str 1..300, "
        "body str non-empty, cta str, hashtags list[str], "
        "suggested_send_at str|null.\n\n"
        "INPUT brief:\n"
        f"{json.dumps(_brief_payload(brief), ensure_ascii=False, indent=2)}\n\n"
        "INPUT value_proposition:\n"
        f"{json.dumps(_value_prop_payload(value_prop), ensure_ascii=False, indent=2)}\n\n"
        "INPUT channels:\n"
        f"{json.dumps(channels.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
        "INPUT keyword_plan:\n"
        f"{json.dumps(keyword_plan.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
        "Return only the JSON object {\"items\": [...]}."
    )


def email_sequence_prompt(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    audience: TargetAudience,
) -> str:
    return (
        "Produce a JSON object that validates against the EmailSequenceDraft "
        "schema (fields: sequence_name str, goal str, audience_label str, "
        "emails list[EmailDraft]). Each EmailDraft has fields: email_id str, "
        "step int>=1, subject str 1..80, preview_text str 1..140, body str "
        "non-empty, cta str, send_after_days int>=0.\n\n"
        "INPUT brief:\n"
        f"{json.dumps(_brief_payload(brief), ensure_ascii=False, indent=2)}\n\n"
        "INPUT value_proposition:\n"
        f"{json.dumps(_value_prop_payload(value_prop), ensure_ascii=False, indent=2)}\n\n"
        "INPUT audience:\n"
        f"{json.dumps(_audience_payload(audience), ensure_ascii=False, indent=2)}\n\n"
        "Return only the JSON object."
    )


def reels_script_pack_prompt(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    audience: TargetAudience,
) -> str:
    return (
        "Produce a JSON object that validates against the ReelsScriptPack "
        "schema (fields: scripts list[ReelsScriptEntry], "
        "overall_tone str|null). Each ReelsScriptEntry "
        "has: script_id str, title str, hook str 1..200, beats list[str], "
        "voiceover_lines list[str], on_screen_text list[str], cta str, "
        "target_duration_s int 10..90.\n\n"
        "INPUT brief:\n"
        f"{json.dumps(_brief_payload(brief), ensure_ascii=False, indent=2)}\n\n"
        "INPUT value_proposition:\n"
        f"{json.dumps(_value_prop_payload(value_prop), ensure_ascii=False, indent=2)}\n\n"
        "INPUT audience:\n"
        f"{json.dumps(_audience_payload(audience), ensure_ascii=False, indent=2)}\n\n"
        "Return only the JSON object."
    )


__all__ = [
    "SYSTEM_PROMPT",
    "campaign_strategy_prompt",
    "creative_brief_pack_prompt",
    "email_sequence_prompt",
    "reels_script_pack_prompt",
    "social_post_drafts_prompt",
    "value_proposition_prompt",
]
