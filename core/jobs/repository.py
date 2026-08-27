"""Job persistence (MKT-11C).

One file per job under ``kind="job"`` — **no singleton entity id**. Every
job keeps its own history forever; nothing is ever overwritten in place
except the record's own state as it advances (the file at ``job_id`` is
rewritten on each transition, but no other job's file is ever touched).

Multi-tenant isolation is inherited for free from ``JsonFileMemory``'s
per-client directory layout plus ``validate_slug`` — the same mechanism
every other kind in this codebase relies on.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from core.memory import EntityNotFound, Memory

from .models import JOB_KIND, JobRecord

_REDACTED_MARKER = "***redacted***"


def sanitize_params(params: dict, sensitive_fields: frozenset[str]) -> dict:
    """Replace every key in ``sensitive_fields`` with a fixed marker.

    Applied to every job's params dict before it is persisted, regardless
    of whether the operation declares any sensitive fields today — this is
    the single choke point future connectors (GA4 / Google Ads / Meta Ads
    credentials) must rely on instead of inventing per-operation
    redaction. Never raises on an absent field.
    """
    if not sensitive_fields:
        return dict(params)
    return {
        k: (_REDACTED_MARKER if k in sensitive_fields else v)
        for k, v in params.items()
    }


class JobPersistenceError(RuntimeError):
    """The stored job record exists but could not be read back — corrupted
    JSON or a schema mismatch. Distinct from "job not found"."""

    def __init__(self, job_id: str, reason: str) -> None:
        self.job_id = job_id
        self.reason = reason
        super().__init__(f"job {job_id!r} could not be read: {reason}")


class JobRepository:
    """Thin persistence wrapper around :class:`~core.memory.Memory` scoped
    to the ``job`` kind. No business logic — the runner and service layer
    own the state machine; this module only reads and writes records."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def save(self, record: JobRecord) -> None:
        self._memory.put(
            record.client_slug, JOB_KIND, record.job_id,
            record.model_dump(mode="json"),
        )

    def get(self, client_slug: str, job_id: str) -> JobRecord:
        """Raises ``EntityNotFound`` when absent, ``JobPersistenceError``
        when the stored record cannot be deserialised (corrupted JSON or
        a schema mismatch)."""
        try:
            raw = self._memory.get(client_slug, JOB_KIND, job_id)
        except EntityNotFound:
            raise
        except json.JSONDecodeError as e:
            raise JobPersistenceError(job_id, str(e)) from e
        try:
            return JobRecord.model_validate(raw)
        except ValidationError as e:
            raise JobPersistenceError(job_id, str(e)) from e

    def list_for_client(
        self,
        client_slug: str,
        *,
        state: str | None = None,
        operation: str | None = None,
        limit: int | None = None,
    ) -> list[JobRecord]:
        """All jobs for one tenant, newest first (``created_at`` descending,
        ``job_id`` as a stable tiebreaker).

        **Corruption tolerance, honestly scoped:** ``Memory.list()`` reads
        every file for this kind in one pass and raises on the first
        invalid JSON byte — the underlying ABC gives no per-file recovery
        point, so a syntactically corrupted file fails the whole listing
        (raises :class:`JobPersistenceError`, never an unhandled
        traceback). A file that IS valid JSON but fails the
        :class:`~core.jobs.models.JobRecord` schema is skipped
        individually, since that failure happens after the bulk read
        already succeeded and each record can be validated on its own.
        """
        try:
            raws = self._memory.list(client_slug, JOB_KIND)
        except json.JSONDecodeError as e:
            raise JobPersistenceError(
                client_slug, f"a job record for this client is corrupted: {e}",
            ) from e
        records: list[JobRecord] = []
        for raw in raws:
            try:
                record = JobRecord.model_validate(raw)
            except ValidationError:
                continue
            if state is not None and record.state.value != state:
                continue
            if operation is not None and record.operation != operation:
                continue
            records.append(record)
        records.sort(key=lambda r: (r.created_at, r.job_id), reverse=True)
        if limit is not None:
            records = records[:limit]
        return records


__all__ = [
    "JobPersistenceError",
    "JobRepository",
    "sanitize_params",
]
