"""JsonFileMemory — filesystem-backed default :class:`Memory` implementation.

Storage layout (see ``docs/storage-layout.md``):

    <root>/<client_slug>/
        _meta.json                      # backend metadata
        <kind>/<entity_id>.json         # one JSON per entity
        audit/
            YYYY-MM-DD.jsonl            # one JSONL per UTC day, append-only
            _chain_tail.txt             # hex hash of the last appended event

Writes are atomic on POSIX and Windows via "write to temp + os.replace".

Audit appends (job-execution-robustness): the full
read-tail -> validate prev_hash -> append line -> update tail sequence is
one critical section, protected by a per-client
:class:`~core.memory.filelock.FileLock` (``<client>/_locks/audit.lock`` —
a separate path from any job's execution lock; a job's lock protects one
job, this protects one client's whole audit stream, since two DIFFERENT
jobs for the same client legitimately write to it concurrently). Acquired
with a bounded, cross-platform poll-based wait — never an indefinite
hang, never a raw ``OSError``/``PermissionError`` surfacing to the
caller; a real timeout raises :class:`~core.memory.filelock.LockTimeoutError`.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.contracts import AuditTrailEvent
from core.domain.base import validate_slug

from .base import MEMORY_CONTRACT_VERSION, Memory, validate_kind
from .errors import AuditChainError, EntityNotFound
from .filelock import FileLock

_AUDIT_LOCK_TIMEOUT_SECONDS = 10.0

# Entity ids appear in file names. Restrict to a safe alphabet to prevent
# directory traversal and odd filesystem behavior.
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _validate_entity_id(entity_id: str) -> str:
    if not isinstance(entity_id, str) or not _ID_RE.match(entity_id):
        raise ValueError(
            f"invalid entity_id {entity_id!r}: must match [A-Za-z0-9._-]{{1,128}}"
        )
    return entity_id


def _atomic_write(target: Path, data: str, encoding: str = "utf-8") -> None:
    """Write ``data`` to ``target`` atomically.

    Uses ``tempfile`` in the same directory + ``os.replace`` so the file
    appears in its final state or not at all.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    # delete=False so we control the rename; we close the handle before replace.
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


class JsonFileMemory(Memory):
    """Filesystem-backed Memory.

    Args:
        root: directory under which client folders are created. Typically
            ``Path("data/clients")`` relative to the repo root.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    # -------- path helpers --------

    def _client_dir(self, client_slug: str) -> Path:
        validate_slug(client_slug)
        return self._root / client_slug

    def _kind_dir(self, client_slug: str, kind: str) -> Path:
        validate_kind(kind)
        return self._client_dir(client_slug) / kind

    def _entity_path(self, client_slug: str, kind: str, entity_id: str) -> Path:
        _validate_entity_id(entity_id)
        return self._kind_dir(client_slug, kind) / f"{entity_id}.json"

    def _audit_dir(self, client_slug: str) -> Path:
        return self._client_dir(client_slug) / "audit"

    def _audit_day_path(self, client_slug: str, day: date) -> Path:
        return self._audit_dir(client_slug) / f"{day.isoformat()}.jsonl"

    def _chain_tail_path(self, client_slug: str) -> Path:
        return self._audit_dir(client_slug) / "_chain_tail.txt"

    def _audit_lock_path(self, client_slug: str) -> Path:
        return self._client_dir(client_slug) / "_locks" / "audit.lock"

    def _meta_path(self, client_slug: str) -> Path:
        return self._client_dir(client_slug) / "_meta.json"

    def _ensure_meta(self, client_slug: str) -> None:
        meta = self._meta_path(client_slug)
        if meta.exists():
            return
        payload = {
            "contract_version": MEMORY_CONTRACT_VERSION,
            "client_slug": client_slug,
            "created_at": datetime.now().astimezone().isoformat(),
        }
        _atomic_write(meta, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    # -------- entity CRUD --------

    def put(
        self, client_slug: str, kind: str, entity_id: str, data: dict[str, Any]
    ) -> None:
        path = self._entity_path(client_slug, kind, entity_id)
        self._ensure_meta(client_slug)
        _atomic_write(path, json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")

    def get(self, client_slug: str, kind: str, entity_id: str) -> dict[str, Any]:
        path = self._entity_path(client_slug, kind, entity_id)
        if not path.exists():
            raise EntityNotFound(client_slug, kind, entity_id)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def list(self, client_slug: str, kind: str) -> list[dict[str, Any]]:
        kind_dir = self._kind_dir(client_slug, kind)
        if not kind_dir.exists():
            return []
        out: list[dict[str, Any]] = []
        # Stable order: sorted by filename (== entity_id).
        for f in sorted(kind_dir.glob("*.json")):
            with f.open("r", encoding="utf-8") as fh:
                out.append(json.load(fh))
        return out

    def exists(self, client_slug: str, kind: str, entity_id: str) -> bool:
        return self._entity_path(client_slug, kind, entity_id).exists()

    def delete(self, client_slug: str, kind: str, entity_id: str) -> None:
        path = self._entity_path(client_slug, kind, entity_id)
        if not path.exists():
            raise EntityNotFound(client_slug, kind, entity_id)
        path.unlink()

    # -------- audit trail --------

    def append_audit_event(self, event: AuditTrailEvent) -> None:
        """Append a pre-built event. The write itself (append line +
        update chain tail) is protected by the per-client audit lock, so
        this can no longer corrupt the tail file under concurrent writers
        (the original bug this module's job-execution-robustness work
        fixed). It does **not** close the earlier race window: whichever
        code built ``event`` computed its ``prev_hash`` by calling
        :meth:`last_audit_hash` *before* this method — and therefore
        before this lock — was acquired. Two concurrent callers using
        this method directly can still both read the same tail and both
        build an event chained to it; the second one to reach the lock
        here will correctly raise :class:`AuditChainError` (loud,
        structured, never silent corruption) rather than succeed, but
        that caller's work is lost, not retried.

        :meth:`append_audit_event_atomic` closes that window completely by
        building the event *inside* the lock. As of the job-execution-
        robustness GAP 1 follow-up, every productive audit writer in
        ``core/`` and ``cli/`` uses that method — this one (LOW-LEVEL /
        LEGACY API, see the base-class docstring) is kept only for backward
        compatibility and must not be used by new callers or current
        runtime paths.
        """
        if event.client_slug is None:
            raise ValueError(
                "JsonFileMemory.append_audit_event requires event.client_slug "
                "to be set (storage is multi-tenant)"
            )
        client_slug = event.client_slug
        validate_slug(client_slug)

        lock = FileLock(self._audit_lock_path(client_slug))
        lock.acquire(timeout=_AUDIT_LOCK_TIMEOUT_SECONDS)
        try:
            self._append_audit_event_locked(event)
        finally:
            lock.release()

    def append_audit_event_atomic(
        self, client_slug: str, build_event: Callable[[str | None], AuditTrailEvent],
    ) -> AuditTrailEvent:
        """Read the current chain tail, build the event from it, and
        append it — all inside one held lock, so the ``prev_hash`` the
        event is chained to is guaranteed still current at write time.
        ``build_event(prev_hash)`` must construct and return the fully
        chained :class:`AuditTrailEvent` (its own ``.hash`` already
        computed from that ``prev_hash``) — this method does not, and
        cannot, patch an already-built event's hash after the fact.
        Returns the event that was actually appended.
        """
        validate_slug(client_slug)
        lock = FileLock(self._audit_lock_path(client_slug))
        lock.acquire(timeout=_AUDIT_LOCK_TIMEOUT_SECONDS)
        try:
            prev = self.last_audit_hash(client_slug)
            event = build_event(prev)
            if event.client_slug != client_slug:
                raise ValueError(
                    f"build_event returned an event for client_slug="
                    f"{event.client_slug!r}, expected {client_slug!r}"
                )
            self._append_audit_event_locked(event)
            return event
        finally:
            lock.release()

    def _append_audit_event_locked(self, event: AuditTrailEvent) -> None:
        """Write side only — caller MUST already hold the per-client audit
        lock. Validates prev_hash against the (still-locked, so still
        current) tail, appends the line, updates the tail atomically."""
        client_slug = event.client_slug
        assert client_slug is not None  # enforced by both public callers above

        last = self.last_audit_hash(client_slug)
        if event.prev_hash != last:
            raise AuditChainError(
                f"prev_hash mismatch for client {client_slug!r}: "
                f"event.prev_hash={event.prev_hash!r} stored_tail={last!r}"
            )

        day_path = self._audit_day_path(client_slug, event.occurred_at.date())
        day_path.parent.mkdir(parents=True, exist_ok=True)
        line = event.to_json() + "\n"
        # Append-only: O_APPEND semantics via "a" mode.
        with day_path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        # Update chain tail atomically.
        _atomic_write(self._chain_tail_path(client_slug), event.hash + "\n")

    def read_audit_events(
        self, client_slug: str, day: date | None = None
    ) -> list[AuditTrailEvent]:
        validate_slug(client_slug)
        audit_dir = self._audit_dir(client_slug)
        if not audit_dir.exists():
            return []

        if day is not None:
            files = [self._audit_day_path(client_slug, day)]
        else:
            files = sorted(audit_dir.glob("*.jsonl"))

        events: list[AuditTrailEvent] = []
        for path in files:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                for lineno, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        events.append(AuditTrailEvent.from_json(raw))
                    except Exception as e:  # noqa: BLE001
                        raise AuditChainError(
                            f"corrupt audit JSONL at {path}:{lineno}: {e}"
                        ) from e
        return events

    def last_audit_hash(self, client_slug: str) -> str | None:
        validate_slug(client_slug)
        tail = self._chain_tail_path(client_slug)
        if not tail.exists():
            return None
        text = tail.read_text(encoding="utf-8").strip()
        return text or None
