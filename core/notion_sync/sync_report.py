"""Pydantic models for the Notion sync report (MKT-5B).

Contract: ``notion-sync-report.v1``.

A sync report is the post-execution counterpart of the dry-run
:class:`NotionSyncPlan` (MKT-5A). It records:

- The mode the operator ran in (``dry_run`` / ``write``).
- Whether the write was actually attempted (gated by
  ``--confirm`` + env vars + SDK availability).
- Per-task outcome (``created`` / ``skipped_blocked`` /
  ``skipped_invalid`` / ``skipped_already_synced`` /
  ``skipped_refused`` / ``failed``).
- A flat list of :class:`NotionWriteAttempt` instances for full
  traceability — model id, request id, duration, ok flag — never
  the token, never the prompt body.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

NOTION_SYNC_REPORT_VERSION = "notion-sync-report.v1"


class SyncMode(StrEnum):
    DRY_RUN = "dry_run"
    WRITE = "write"


class SyncedRecordOutcome(StrEnum):
    """Per-task result of running the executor."""

    CREATED = "created"
    SKIPPED_BLOCKED = "skipped_blocked"
    SKIPPED_INVALID = "skipped_invalid"
    SKIPPED_ALREADY_SYNCED = "skipped_already_synced"
    SKIPPED_REFUSED = "skipped_refused"
    """Writer was wired but refused (no token / no SDK / not
    confirmed); the executor records the task without attempting
    the call."""

    FAILED = "failed"
    """The writer attempted the call and the SDK raised."""


class SyncedRecord(DomainModel):
    task_id: Annotated[str, Field(min_length=1, max_length=120)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    outcome: SyncedRecordOutcome
    page_id: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=400)
    duration_ms: float | None = Field(default=None, ge=0.0)
    error_type: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=200)


class SyncStats(DomainModel):
    total_records: int = Field(ge=0)
    created: int = Field(ge=0)
    skipped_blocked: int = Field(ge=0)
    skipped_invalid: int = Field(ge=0)
    skipped_already_synced: int = Field(ge=0)
    skipped_refused: int = Field(ge=0)
    failed: int = Field(ge=0)


class NotionSyncReport(DomainModel):
    """End-to-end report of one ``mkt notion-sync`` execution."""

    contract_version: Literal["notion-sync-report.v1"] = NOTION_SYNC_REPORT_VERSION
    report_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    plan_id: str = Field(min_length=1)
    plan_contract_version: str = Field(min_length=1)
    task_pack_id: str = Field(min_length=1)

    mode: SyncMode
    confirmed: bool
    """Whether the operator passed ``--confirm`` (only meaningful
    when ``mode == WRITE``)."""

    write_attempted: bool
    """Whether the executor wired a real :class:`NotionWriter`. May
    be True with zero records actually written if all tasks were
    filtered upstream."""

    write_blocked_reason: str | None = Field(default=None, max_length=400)
    """Non-None when ``mode == WRITE`` but the executor fell back
    to dry-run anyway (missing token, missing SDK, plan has errors).
    Surfaced loudly in the Markdown + on stderr by the CLI."""

    token_env_present: bool
    database_id_env_present: bool
    sdk_available: bool

    records: list[SyncedRecord] = Field(default_factory=list)
    stats: SyncStats

    started_at: datetime
    finished_at: datetime
    rule_set_id: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("started_at", "finished_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


# ---------- per-client page mapping (idempotency) ----------

NOTION_SYNCED_PAGES_KIND = "notion_synced_pages"
NOTION_SYNCED_PAGES_SINGLETON_ID = "current"


class NotionSyncedPageEntry(DomainModel):
    """One row in the task_id → page_id map persisted per client.

    Idempotency mechanism: the executor refuses to re-create a
    Notion page for a task that's already in this map. Operator
    can clear the map manually if they want to re-sync (e.g.
    after deleting Notion pages by hand).
    """

    task_id: Annotated[str, Field(min_length=1, max_length=120)]
    page_id: Annotated[str, Field(min_length=1, max_length=120)]
    synced_at: datetime
    sync_report_id: str = Field(min_length=1)


class NotionSyncedPagesIndex(DomainModel):
    """The per-client ``task_id → NotionSyncedPageEntry`` map."""

    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    entries: list[NotionSyncedPageEntry] = Field(default_factory=list)
    updated_at: datetime

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware (UTC)")
        return v

    def as_dict(self) -> dict[str, NotionSyncedPageEntry]:
        return {e.task_id: e for e in self.entries}


__all__ = [
    "NOTION_SYNC_REPORT_VERSION",
    "NOTION_SYNCED_PAGES_KIND",
    "NOTION_SYNCED_PAGES_SINGLETON_ID",
    "NotionSyncReport",
    "NotionSyncedPageEntry",
    "NotionSyncedPagesIndex",
    "SyncMode",
    "SyncStats",
    "SyncedRecord",
    "SyncedRecordOutcome",
]
