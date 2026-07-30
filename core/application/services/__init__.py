"""Application services (MKT-11A).

Scope of this milestone: SEO Intelligence Report, Analytics snapshot
reads, and Approvals. See
``docs/MKT-11A-Application-Services-Inventory.md`` for the commands
deliberately left unmigrated.
"""

from __future__ import annotations

from . import analytics, approvals, seo

__all__ = ["analytics", "approvals", "seo"]
