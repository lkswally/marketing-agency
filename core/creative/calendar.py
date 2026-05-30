"""Per-piece publishing calendar.

The calendar in MKT-3A is a channel-level cadence ("LinkedIn: 3 posts /
week"). Here we go one level deeper: every concrete asset gets a date
inside the campaign window, so a human reviewer can see "when does each
specific email / post / reel ship".

Pure, deterministic: same campaign duration + same asset list → same
schedule.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from core.domain.enums import ChannelType

from .models import (
    CalendarEntry,
    CreativeAssetKind,
    EmailAsset,
    FlyerAsset,
    ReelsAsset,
    SocialPostAsset,
)

# Default publishing days per channel type. Mondays and Thursdays for
# owned channels; weekly for newsletter / blog; daily-ish for social.
_DEFAULT_WEEKDAYS: dict[ChannelType, list[int]] = {
    ChannelType.NEWSLETTER: [3],  # Thursday
    ChannelType.BLOG: [1],  # Tuesday
    ChannelType.LINKEDIN: [1, 3],  # Tue + Thu
    ChannelType.X: [0, 2, 4],  # Mon, Wed, Fri
    ChannelType.INSTAGRAM: [1, 4],  # Tue + Fri
    ChannelType.TIKTOK: [2, 4],  # Wed + Fri
    ChannelType.YOUTUBE: [3],  # Thursday
    ChannelType.PODCAST: [1],  # Tuesday
    ChannelType.FACEBOOK: [1, 3],
    ChannelType.PAID_SEARCH: [0],
    ChannelType.PAID_SOCIAL: [0],
    ChannelType.EMAIL: [3],
    ChannelType.DISPLAY: [0],
    ChannelType.SEO: [1],
    ChannelType.PR: [1],
    ChannelType.OTHER: [1],
}


def _aligned_date(start: date, week: int, weekday: int) -> date:
    """Return the date for ``weekday`` in week ``week`` (1-indexed) from ``start``."""
    # Move ``start`` to the Monday of its week.
    monday = start - timedelta(days=start.weekday())
    # Week ``week`` Monday + offset to the desired weekday.
    return monday + timedelta(weeks=week - 1, days=weekday)


def schedule_assets(
    *,
    social_posts: Iterable[SocialPostAsset],
    emails: Iterable[EmailAsset],
    reels: Iterable[ReelsAsset],
    flyers: Iterable[FlyerAsset],
    start_date: date,
    end_date: date,
) -> tuple[list[CalendarEntry], dict[str, date | None]]:
    """Build a deterministic calendar for the supplied assets.

    Returns a tuple ``(entries, asset_to_date)`` where ``asset_to_date`` maps
    each asset id to its assigned date (or ``None`` if it could not be
    placed). The auditor can use this to backfill ``scheduled_for`` on the
    asset instances.

    Strategy:
    - Emails are placed sequentially from ``start_date`` using
      ``send_after_days`` (already an offset).
    - Social posts are distributed across the campaign window using each
      channel's preferred weekdays.
    - Reels share Instagram / TikTok weekdays.
    - Flyers are placed on Tuesdays (one per week starting at week 1).
    """
    entries: list[CalendarEntry] = []
    asset_dates: dict[str, date | None] = {}

    weeks_total = max(
        1, ((end_date - start_date).days // 7) + 1
    )

    # ---- emails ----
    for email in emails:
        when = start_date + timedelta(days=email.send_after_days)
        if when > end_date:
            when = end_date
        # Compute the week relative to start_date.
        week = max(1, min(weeks_total, ((when - start_date).days // 7) + 1))
        entries.append(
            CalendarEntry(
                asset_id=email.asset_id,
                asset_kind=CreativeAssetKind.EMAIL,
                week=week,
                scheduled_for=when,
                channel=ChannelType.NEWSLETTER,
                cadence_note=f"Email #{email.step}",
            )
        )
        asset_dates[email.asset_id] = when

    # ---- social posts ----
    # Round-robin across the campaign weeks.
    social_by_channel: dict[ChannelType, list[SocialPostAsset]] = {}
    for p in social_posts:
        social_by_channel.setdefault(p.channel, []).append(p)

    for channel, posts in social_by_channel.items():
        weekdays = _DEFAULT_WEEKDAYS.get(channel, [1])
        for idx, post in enumerate(posts):
            week = (idx // len(weekdays)) + 1
            week = min(week, weeks_total)
            weekday = weekdays[idx % len(weekdays)]
            when = _aligned_date(start_date, week, weekday)
            if when > end_date:
                when = end_date
            entries.append(
                CalendarEntry(
                    asset_id=post.asset_id,
                    asset_kind=CreativeAssetKind.SOCIAL_POST,
                    week=week,
                    scheduled_for=when,
                    channel=channel,
                    cadence_note=f"{channel.value} post #{idx + 1}",
                )
            )
            asset_dates[post.asset_id] = when

    # ---- reels ----
    # Spread across the schedule on Wednesdays (Instagram + TikTok weekday 2).
    reels_list = list(reels)
    for idx, r in enumerate(reels_list):
        week = min(weeks_total, idx + 1)
        when = _aligned_date(start_date, week, 2)
        if when > end_date:
            when = end_date
        entries.append(
            CalendarEntry(
                asset_id=r.asset_id,
                asset_kind=CreativeAssetKind.REELS_SCRIPT,
                week=week,
                scheduled_for=when,
                channel=ChannelType.INSTAGRAM,
                cadence_note=f"Reels #{idx + 1}",
            )
        )
        asset_dates[r.asset_id] = when

    # ---- flyers ----
    flyers_list = list(flyers)
    for idx, f in enumerate(flyers_list):
        week = min(weeks_total, idx + 1)
        when = _aligned_date(start_date, week, 1)  # Tuesday
        if when > end_date:
            when = end_date
        entries.append(
            CalendarEntry(
                asset_id=f.asset_id,
                asset_kind=CreativeAssetKind.FLYER_COPY,
                week=week,
                scheduled_for=when,
                channel=None,
                cadence_note=f"Flyer #{idx + 1} ({f.format.value})",
            )
        )
        asset_dates[f.asset_id] = when

    # Sort by date for predictability.
    entries.sort(key=lambda e: (e.scheduled_for, e.week, e.asset_kind.value))

    return entries, asset_dates


__all__ = ["schedule_assets"]
