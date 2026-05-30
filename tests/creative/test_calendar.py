"""Calendar tests — scheduling determinism + structural shape."""

from __future__ import annotations

from datetime import date, timedelta

from core.creative import (
    CTAStyle,
    CTAVariant,
    EmailAsset,
    FlyerAsset,
    FlyerFormat,
    HeadlineStyle,
    HeadlineVariant,
    HookVariant,
    ReelsAsset,
    SocialPostAsset,
    SubjectLineVariant,
    SubjectStyle,
    VariantAngle,
)
from core.creative.calendar import schedule_assets
from core.domain.enums import ChannelType


def _social(channel: ChannelType, asset_id: str = "s1") -> SocialPostAsset:
    return SocialPostAsset(
        asset_id=asset_id,
        channel=channel,
        hook_variants=[HookVariant(variant_id="A", text="x", angle=VariantAngle.CURIOSITY)],
        body="b",
        cta_variants=[CTAVariant(variant_id="A", text="go", style=CTAStyle.DIRECT)],
    )


def _email(step: int, send_after: int) -> EmailAsset:
    return EmailAsset(
        asset_id=f"e{step}",
        step=step,
        subject_line_variants=[
            SubjectLineVariant(
                variant_id="A", subject="s", preview_text="p", style=SubjectStyle.DIRECT
            )
        ],
        body="b",
        cta="c",
        send_after_days=send_after,
    )


def _reels(idx: int) -> ReelsAsset:
    return ReelsAsset(
        asset_id=f"r{idx}",
        title=f"R{idx}",
        hook_variants=[HookVariant(variant_id="A", text="x", angle=VariantAngle.CURIOSITY)],
        beats=["0-3s: hook"],
        cta="c",
        target_duration_s=30,
    )


def _flyer(idx: int) -> FlyerAsset:
    return FlyerAsset(
        asset_id=f"f{idx}",
        format=FlyerFormat.SQUARE,
        headline_variants=[
            HeadlineVariant(variant_id="A", text="x", style=HeadlineStyle.BENEFIT)
        ],
        subhead="s",
        body="b",
        cta="c",
    )


# ---------- structural ----------

def test_emails_scheduled_using_send_after_days() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(weeks=8)
    e1 = _email(1, 0)
    e2 = _email(2, 7)
    entries, dates = schedule_assets(
        social_posts=[], emails=[e1, e2], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    assert dates[e1.asset_id] == start
    assert dates[e2.asset_id] == start + timedelta(days=7)
    assert all(e.asset_kind.value == "email" for e in entries)


def test_social_posts_distributed_by_weekday() -> None:
    start = date(2026, 6, 1)  # Monday
    end = start + timedelta(weeks=4)
    posts = [_social(ChannelType.LINKEDIN, asset_id=f"p{i}") for i in range(4)]
    entries, dates = schedule_assets(
        social_posts=posts, emails=[], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    # LinkedIn weekdays default to Tue + Thu (indices 1, 3).
    for entry in entries:
        weekday = entry.scheduled_for.weekday()
        assert weekday in {1, 3}


def test_reels_on_wednesday() -> None:
    start = date(2026, 6, 1)  # Monday
    end = start + timedelta(weeks=4)
    reels = [_reels(i) for i in range(2)]
    entries, _ = schedule_assets(
        social_posts=[], emails=[], reels=reels, flyers=[],
        start_date=start, end_date=end,
    )
    assert all(e.scheduled_for.weekday() == 2 for e in entries)
    assert all(e.asset_kind.value == "reels_script" for e in entries)


def test_flyers_on_tuesday() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(weeks=4)
    flyers = [_flyer(i) for i in range(2)]
    entries, _ = schedule_assets(
        social_posts=[], emails=[], reels=[], flyers=flyers,
        start_date=start, end_date=end,
    )
    assert all(e.scheduled_for.weekday() == 1 for e in entries)


def test_entries_sorted_by_date() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(weeks=8)
    entries, _ = schedule_assets(
        social_posts=[_social(ChannelType.LINKEDIN), _social(ChannelType.INSTAGRAM)],
        emails=[_email(1, 0), _email(2, 14)],
        reels=[_reels(1)],
        flyers=[_flyer(1)],
        start_date=start, end_date=end,
    )
    dates_in_order = [e.scheduled_for for e in entries]
    assert dates_in_order == sorted(dates_in_order)


# ---------- determinism ----------

def test_schedule_is_deterministic() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(weeks=4)
    posts = [_social(ChannelType.X, asset_id=f"p{i}") for i in range(3)]
    a, _ = schedule_assets(
        social_posts=posts, emails=[], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    b, _ = schedule_assets(
        social_posts=posts, emails=[], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    assert [e.scheduled_for for e in a] == [e.scheduled_for for e in b]


# ---------- end date clamp ----------

def test_send_after_exceeding_window_clamps_to_end() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(days=7)
    e = _email(1, 999)  # way past end
    _, dates = schedule_assets(
        social_posts=[], emails=[e], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    assert dates[e.asset_id] == end


# ---------- empty inputs ----------

def test_empty_inputs_produce_empty_calendar() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(weeks=4)
    entries, dates = schedule_assets(
        social_posts=[], emails=[], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    assert entries == []
    assert dates == {}


# ---------- week assignment ----------

def test_week_is_one_indexed() -> None:
    start = date(2026, 6, 1)
    end = start + timedelta(weeks=4)
    entries, _ = schedule_assets(
        social_posts=[], emails=[_email(1, 0)], reels=[], flyers=[],
        start_date=start, end_date=end,
    )
    assert entries[0].week == 1
