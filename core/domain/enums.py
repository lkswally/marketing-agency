"""Enums shared across MKT domain models.

Contract: domain-model.v1
All enums inherit from (str, Enum) so they serialize to plain strings in JSON.
"""

from __future__ import annotations

from enum import StrEnum


class ChannelType(StrEnum):
    EMAIL = "email"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    X = "x"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    BLOG = "blog"
    NEWSLETTER = "newsletter"
    PAID_SEARCH = "paid_search"
    PAID_SOCIAL = "paid_social"
    DISPLAY = "display"
    SEO = "seo"
    PR = "pr"
    OTHER = "other"


class AssetType(StrEnum):
    LOGO = "logo"
    IMAGE = "image"
    VIDEO = "video"
    COPY = "copy"
    EMAIL_TEMPLATE = "email_template"
    LANDING = "landing"
    DECK = "deck"
    PDF = "pdf"
    AUDIO = "audio"
    OTHER = "other"


class ClaimSeverity(StrEnum):
    """Risk level of a claim. UNSAFE blocks output emission; RISKY requires override."""

    SAFE = "safe"
    CAVEAT = "caveat"
    RISKY = "risky"
    UNSAFE = "unsafe"


class ClaimVerdict(StrEnum):
    """Result of a claim validation pass."""

    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"


class MetricUnit(StrEnum):
    COUNT = "count"
    PERCENT = "percent"
    CURRENCY = "currency"
    SECONDS = "seconds"
    SCORE = "score"
    RATIO = "ratio"
    OTHER = "other"


class MetricSource(StrEnum):
    """Origin of a measurement. No connector implementations exist yet."""

    GA4 = "ga4"
    SOCIAL = "social"
    EMAIL = "email"
    SEARCH_SEO = "search_seo"
    PUBLIC_FOOTPRINT = "public_footprint"
    MANUAL = "manual"
    INTERNAL_REPORT = "internal_report"


class MetricCategory(StrEnum):
    """What the metric measures, regardless of source."""

    ACQUISITION = "acquisition"
    ENGAGEMENT = "engagement"
    CONVERSION = "conversion"
    REACH = "reach"
    RETENTION = "retention"
    BRAND = "brand"
    SEO = "seo"


class SubjectType(StrEnum):
    """The kind of entity a metric or snapshot is about."""

    CLIENT = "client"
    COMPETITOR = "competitor"
    CHANNEL = "channel"
    CAMPAIGN = "campaign"
    ASSET = "asset"
    PERSONA = "persona"
    AUDIENCE = "audience"


class BriefStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CampaignStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OfferType(StrEnum):
    PRODUCT = "product"
    SERVICE = "service"
    SUBSCRIPTION = "subscription"
    LEAD_MAGNET = "lead_magnet"
    BUNDLE = "bundle"
    OTHER = "other"


class BacklogStatus(StrEnum):
    PROPOSED = "proposed"
    PRIORITIZED = "prioritized"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DISCARDED = "discarded"


class ReportType(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    CAMPAIGN_RECAP = "campaign_recap"
    ADHOC = "adhoc"


class EvidenceSourceType(StrEnum):
    URL = "url"
    INTERNAL_DOC = "internal_doc"
    DATASET = "dataset"
    QUOTE = "quote"
    OTHER = "other"
