"""MKT canonical domain model.

Contract: domain-model.v1 (see docs/contracts/domain-model.md).

All entities are Pydantic v2 models. Entities reference each other by id or
slug; the model layer does NOT enforce cross-entity referential integrity —
that is the responsibility of the repository layer (MKT-1D+).
"""

from __future__ import annotations

from .asset import Asset
from .audience import Audience
from .backlog import GrowthBacklogItem
from .base import DomainModel, TimestampedModel, new_id, utcnow, validate_slug
from .brand import Brand, BrandVoice
from .brief import MarketingBrief
from .campaign import Campaign
from .channel import Channel
from .claim import Claim
from .client import Client
from .competitor import Competitor
from .enums import (
    AssetType,
    BacklogStatus,
    BriefStatus,
    CampaignStatus,
    ChannelType,
    ClaimSeverity,
    ClaimVerdict,
    EvidenceSourceType,
    MetricCategory,
    MetricSource,
    MetricUnit,
    OfferType,
    ReportType,
    SubjectType,
)
from .evidence import Evidence
from .footprint import DigitalFootprintSnapshot
from .metric import Metric
from .offer import Offer
from .persona import Persona
from .positioning import Positioning
from .report import Report

__all__ = [
    # Base
    "DomainModel",
    "TimestampedModel",
    "new_id",
    "utcnow",
    "validate_slug",
    # Entities (17)
    "Client",
    "MarketingBrief",
    "Brand",
    "BrandVoice",
    "Audience",
    "Persona",
    "Competitor",
    "Offer",
    "Positioning",
    "Campaign",
    "Channel",
    "Asset",
    "Claim",
    "Evidence",
    "Metric",
    "DigitalFootprintSnapshot",
    "GrowthBacklogItem",
    "Report",
    # Enums
    "AssetType",
    "BacklogStatus",
    "BriefStatus",
    "CampaignStatus",
    "ChannelType",
    "ClaimSeverity",
    "ClaimVerdict",
    "EvidenceSourceType",
    "MetricCategory",
    "MetricSource",
    "MetricUnit",
    "OfferType",
    "ReportType",
    "SubjectType",
]
