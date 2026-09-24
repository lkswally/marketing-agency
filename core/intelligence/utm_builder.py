"""MKT-10X — UTM Builder.

Reads the existing ``CampaignStrategyReport`` from memory and produces a
``UTMPlan`` with one ``UTMTaggedLink`` per channel × piece combination.

UTM parameter derivation rules:
- ``utm_source``   = channel platform slug (e.g. ``instagram``, ``google``)
- ``utm_medium``   = content type slug (e.g. ``social``, ``email``, ``cpc``)
- ``utm_campaign`` = ``<client_slug>-<period>``
- ``utm_content``  = piece title slug (lowercased, spaces → hyphens)
- ``utm_term``     = first keyword from the strategy's keyword plan (when
                     relevant for search channels), else omitted
- ``final_url``    = ``<base_url>?utm_source=…&utm_medium=…&…``

No network calls. No mutations. Pure function over memory + config.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow, validate_slug
from core.memory.base import Memory
from core.memory.errors import EntityNotFound

from .models import (
    UTM_CONTRACT_VERSION,
    TrackingRecommendation,
    UTMPlan,
    UTMTaggedLink,
)

# Memory kinds
UTM_PLAN_KIND = "utm_plan"
SINGLETON_ID = "current"

# Strategy report memory kind (defined in core.strategy.backend)
_STRATEGY_REPORT_KIND = "campaign_strategy_report"

# Channel → (utm_source, utm_medium) mapping
_CHANNEL_UTM: dict[str, tuple[str, str]] = {
    "instagram":       ("instagram",  "social"),
    "facebook":        ("facebook",   "social"),
    "linkedin":        ("linkedin",   "social"),
    "twitter":         ("twitter",    "social"),
    "tiktok":          ("tiktok",     "social"),
    "youtube":         ("youtube",    "video"),
    "email":           ("email",      "email"),
    "newsletter":      ("newsletter", "email"),
    "google_ads":      ("google",     "cpc"),
    "meta_ads":        ("facebook",   "cpc"),
    "linkedin_ads":    ("linkedin",   "cpc"),
    "seo":             ("organic",    "seo"),
    "blog":            ("blog",       "content"),
    "podcast":         ("podcast",    "audio"),
    "whatsapp":        ("whatsapp",   "messaging"),
    "landing_page":    ("direct",     "landing"),
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert free text to a UTM-safe slug."""
    return _SLUG_RE.sub("-", text.lower().strip())[:max_len].strip("-")


def _build_final_url(base_url: str, params: dict[str, str]) -> str:
    """Append UTM params to base_url as query string."""
    sep = "&" if "?" in base_url else "?"
    pairs = "&".join(f"{k}={v}" for k, v in params.items() if v)
    return f"{base_url}{sep}{pairs}"


def _channel_utm(channel_raw: str) -> tuple[str, str]:
    """Return (utm_source, utm_medium) for a channel string."""
    key = channel_raw.lower().replace(" ", "_").replace("-", "_")
    return _CHANNEL_UTM.get(key, (key, "social"))


class UTMBuilder:
    """Builds a :class:`UTMPlan` from a client's stored strategy report.

    Args:
        memory:   A :class:`core.memory.base.Memory` instance.
        base_url: The landing page URL all UTM links will point to.
                  Callers should pass the client's primary landing URL.
    """

    def __init__(self, memory: Memory, *, base_url: str = "https://example.com") -> None:
        self._memory = memory
        self._base_url = base_url

    def build(self, client_slug: str, *, period: str | None = None) -> UTMPlan:
        """Generate a UTM plan for ``client_slug``.

        Reads ``campaign_strategy_report/current`` from memory. If not
        found, produces a minimal plan with a recommendation to run the
        strategy pipeline first.

        Args:
            client_slug: validated slug for the target client.
            period:      optional period label (e.g. ``"2024-Q3"``); defaults
                         to ``YYYY-MM`` of current date.
        """
        validate_slug(client_slug)
        resolved_period = period or utcnow().strftime("%Y-%m")

        strategy_data = self._load_strategy(client_slug)

        if strategy_data is None:
            return self._fallback_plan(client_slug, resolved_period)

        return self._build_from_strategy(client_slug, resolved_period, strategy_data)

    # ------------------------------------------------------------------ #
    # private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _load_strategy(self, client_slug: str) -> dict[str, Any] | None:
        try:
            return self._memory.get(client_slug, _STRATEGY_REPORT_KIND, SINGLETON_ID)
        except EntityNotFound:
            return None

    def _build_from_strategy(
        self,
        client_slug: str,
        period: str,
        strategy: dict[str, Any],
    ) -> UTMPlan:
        campaign_slug = _slugify(f"{client_slug}-{period}")

        # Extract campaign name from strategy
        exec_summary = strategy.get("executive_summary") or {}
        campaign_name = (
            exec_summary.get("campaign_name")
            or exec_summary.get("title")
            or strategy.get("campaign_name")
            or f"{client_slug} {period}"
        )

        # Extract primary keyword for search channels
        kw_plan = strategy.get("keyword_plan") or {}
        clusters = kw_plan.get("clusters") or []
        primary_keyword: str | None = None
        if clusters:
            first_cluster = clusters[0] if isinstance(clusters[0], dict) else {}
            kws = first_cluster.get("keywords") or []
            if kws:
                primary_keyword = kws[0]

        # Build links from suggested_pieces
        tagged_links: list[UTMTaggedLink] = []
        suggested_pieces: list[dict[str, Any]] = strategy.get("suggested_pieces") or []

        for piece in suggested_pieces:
            channel_raw = str(
                (piece.get("channel") or "").replace("ChannelType.", "").lower()
            )
            piece_type = str(piece.get("piece_type") or "content")
            notes_raw = piece.get("notes") or ""

            utm_source, utm_medium = _channel_utm(channel_raw or piece_type)
            utm_content = _slugify(piece_type)
            utm_term = primary_keyword if utm_medium in ("cpc", "seo") else None

            params: dict[str, str] = {
                "utm_source": utm_source,
                "utm_medium": utm_medium,
                "utm_campaign": campaign_slug,
                "utm_content": utm_content,
            }
            if utm_term:
                params["utm_term"] = _slugify(utm_term)

            final_url = _build_final_url(self._base_url, params)

            tagged_links.append(
                UTMTaggedLink(
                    piece_title=piece_type.replace("_", " ").title(),
                    channel=channel_raw or piece_type,
                    base_url=self._base_url,
                    utm_source=utm_source,
                    utm_medium=utm_medium,
                    utm_campaign=campaign_slug,
                    utm_content=utm_content,
                    utm_term=utm_term,
                    final_url=final_url,
                    notes=str(notes_raw) if notes_raw else None,
                )
            )

        # Also build links from channel_recommendation when pieces are sparse
        if not tagged_links:
            channel_rec = strategy.get("channel_recommendation") or {}
            for ch_entry in (channel_rec.get("channels") or []):
                channel_raw = str(
                    (ch_entry.get("channel_type") or "").replace("ChannelType.", "").lower()
                )
                utm_source, utm_medium = _channel_utm(channel_raw)
                utm_content = _slugify(channel_raw)
                params = {
                    "utm_source": utm_source,
                    "utm_medium": utm_medium,
                    "utm_campaign": campaign_slug,
                    "utm_content": utm_content,
                }
                final_url = _build_final_url(self._base_url, params)
                tagged_links.append(
                    UTMTaggedLink(
                        piece_title=channel_raw.replace("_", " ").title(),
                        channel=channel_raw,
                        base_url=self._base_url,
                        utm_source=utm_source,
                        utm_medium=utm_medium,
                        utm_campaign=campaign_slug,
                        utm_content=utm_content,
                        utm_term=None,
                        final_url=final_url,
                    )
                )

        recommendations = self._build_recommendations(tagged_links)
        channels_covered = sorted({lnk.channel for lnk in tagged_links})

        return UTMPlan(
            client_slug=client_slug,
            campaign_name=str(campaign_name),
            period=period,
            tagged_links=tagged_links,
            recommendations=recommendations,
            total_links=len(tagged_links),
            channels_covered=channels_covered,
        )

    def _fallback_plan(self, client_slug: str, period: str) -> UTMPlan:
        """Return a minimal plan when no strategy report exists."""
        recs = [
            TrackingRecommendation(
                priority="high",
                description=(
                    "No campaign strategy report found. Run "
                    "`mkt strategy --client <slug>` first to generate "
                    "UTM links based on real channel recommendations."
                ),
                affected_channels=[],
                action="run_strategy_pipeline",
            )
        ]
        return UTMPlan(
            client_slug=client_slug,
            campaign_name=f"{client_slug} {period}",
            period=period,
            tagged_links=[],
            recommendations=recs,
            total_links=0,
            channels_covered=[],
        )

    @staticmethod
    def _build_recommendations(links: list[UTMTaggedLink]) -> list[TrackingRecommendation]:
        recs: list[TrackingRecommendation] = []
        channels = {lnk.channel for lnk in links}

        if not channels:
            return recs

        # Recommend GA4 integration if not already tracked
        recs.append(
            TrackingRecommendation(
                priority="high",
                description=(
                    "Import these UTM parameters into GA4 as campaign source/medium "
                    "dimensions to track cross-channel conversions."
                ),
                affected_channels=sorted(channels),
                action="configure_ga4_utm_dimensions",
            )
        )

        # Recommend utm_term for search channels missing it
        search_channels_missing_term = [
            lnk.channel
            for lnk in links
            if lnk.utm_medium in ("cpc", "seo") and not lnk.utm_term
        ]
        if search_channels_missing_term:
            recs.append(
                TrackingRecommendation(
                    priority="medium",
                    description=(
                        "Search/CPC channels should include utm_term. "
                        "Run the keyword research skill to populate primary keywords."
                    ),
                    affected_channels=sorted(set(search_channels_missing_term)),
                    action="add_utm_term_for_search_channels",
                )
            )

        return recs


def persist_utm_plan(
    plan: UTMPlan,
    memory: Memory,
    *,
    outputs_root: Path,
) -> tuple[Path, Path]:
    """Persist ``plan`` to memory and write output files.

    Returns:
        Tuple of ``(md_path, json_path)`` for the generated files.
    """
    # Persist to memory
    memory.put(
        plan.client_slug,
        UTM_PLAN_KIND,
        SINGLETON_ID,
        plan.model_dump(mode="json"),
    )

    # Emit audit event
    memory.append_audit_event_atomic(
        plan.client_slug,
        lambda prev_hash_arg: AuditTrailEvent.build(
            event_type=AuditEventType.MEMORY_WRITTEN,
            client_slug=plan.client_slug,
            actor="utm-builder",
            occurred_at=utcnow(),
            payload={
                "kind": UTM_PLAN_KIND,
                "entity_id": SINGLETON_ID,
                "total_links": plan.total_links,
                "channels_covered": plan.channels_covered,
            },
            prev_hash=prev_hash_arg,
        ),
    )

    # Write output files
    out_dir = outputs_root / plan.client_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "utm-plan.json"
    json_path.write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    md_path = out_dir / "utm-plan.md"
    md_path.write_text(_render_markdown(plan), encoding="utf-8")

    return md_path, json_path


def _render_markdown(plan: UTMPlan) -> str:
    lines: list[str] = [
        f"# UTM Plan — {plan.campaign_name}",
        "",
        f"**Client:** `{plan.client_slug}`  ",
        f"**Period:** {plan.period}  ",
        f"**Generated:** {plan.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Total links:** {plan.total_links}  ",
        f"**Channels:** {', '.join(plan.channels_covered) or '—'}",
        "",
    ]

    if plan.tagged_links:
        lines += [
            "## Tagged Links",
            "",
            "| Piece | Channel | Source | Medium | Campaign | Content | Term | Final URL |",
            "|-------|---------|--------|--------|----------|---------|------|-----------|",
        ]
        for lnk in plan.tagged_links:
            term = lnk.utm_term or "—"
            lines.append(
                f"| {lnk.piece_title} | {lnk.channel} | {lnk.utm_source} "
                f"| {lnk.utm_medium} | {lnk.utm_campaign} | {lnk.utm_content} "
                f"| {term} | {lnk.final_url} |"
            )
        lines.append("")

    if plan.recommendations:
        lines += ["## Recommendations", ""]
        for rec in plan.recommendations:
            lines.append(f"- **[{rec.priority.upper()}]** {rec.description}")
            if rec.affected_channels:
                lines.append(f"  - Channels: {', '.join(rec.affected_channels)}")
        lines.append("")

    lines += [
        "---",
        f"_Contract: {UTM_CONTRACT_VERSION}_",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "SINGLETON_ID",
    "UTM_PLAN_KIND",
    "UTMBuilder",
    "persist_utm_plan",
]
