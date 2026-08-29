"""Application services (MKT-11A).

Scope of this milestone: SEO Intelligence Report, Analytics snapshot
reads, and Approvals. See
``docs/MKT-11A-Application-Services-Inventory.md`` for the commands
deliberately left unmigrated.

**MKT-11D note:** this package deliberately does NOT eagerly import its
submodules here (no ``from . import analytics, approvals, jobs, seo``).
``core.jobs.operations.campaign`` depends on
``core.application.services.campaign_run``, and ``core.application.
services.jobs`` registers that very operation on ``core.jobs.default_
registry`` — eagerly aggregating every submodule in this ``__init__``
made that a real circular import, triggerable from more than one entry
point (importing ``core.jobs`` first, or importing ``core.jobs.
operations.campaign`` first). Python resolves ``from core.application.
services import approvals`` (or any other submodule) correctly without
this package pre-importing it — ``from pkg import submodule`` imports
the submodule directly when it is not already a package attribute. Every
existing caller keeps working unchanged; only the (accidental) eager
side effect is removed.
"""

from __future__ import annotations
