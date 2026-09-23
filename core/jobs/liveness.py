"""Stale-``RUNNING`` detection (job-execution-robustness).

**Detection only — never mutates anything.** No auto-resume, no
auto-retry, no automatic transition to ``FAILED``. This module answers
one question: "is the process that set this job to ``RUNNING`` still
actually running, as far as this host's filesystem can tell?" — nothing
more.

The signal is **not** whether a lock file exists on disk (a file left
over from a released lock is not evidence of anything). The signal is:
*can this job's execution lock be acquired right now?* If yes, nothing
currently holds it while the record still says ``RUNNING`` — a crash, by
elimination (the lock, per ``core/memory/filelock.py``, is released by
the OS on any process exit, graceful or not). If no, a real holder has
it — genuinely running.

That signal is only trustworthy for records the *new*, lock-using runner
actually produced. A ``RUNNING`` record from before this mechanism
existed was never protected by any lock — the lock being freely
acquirable for it says nothing about whether that old, unlocked
execution is still alive. :attr:`~core.jobs.models.JobRecord.lock_protected`
is the (additive, backward-compatible) marker that distinguishes the two
cases; see its docstring for why a boolean field was the right minimal
addition instead of inferring this from something less direct, like the
lock file's mere presence or an mtime.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from core.memory.filelock import FileLock

from .models import JobRecord, JobState
from .runner import job_lock_path


class LivenessStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    """``record.state`` is not RUNNING — the question doesn't apply."""

    RUNNING_ACTIVE = "running_active"
    """RUNNING, lock-protected, and the lock is currently held by
    someone — genuinely executing right now, as far as this host can
    tell."""

    STALE = "stale"
    """RUNNING, lock-protected, and the lock is freely acquirable — the
    process that set it RUNNING is gone. No auto-recovery follows from
    this; it is reported, not acted on."""

    UNKNOWN = "unknown"
    """RUNNING, but the record predates this mechanism
    (``lock_protected`` is False) — liveness genuinely cannot be
    determined from the lock, because this record was never protected
    by one. Not a guess in either direction."""


def probe_liveness(root: Path, record: JobRecord) -> LivenessStatus:
    """Read-only. Briefly acquires and releases the job's lock only when
    that's actually informative (state is RUNNING and lock_protected) —
    never for any other state, never mutates ``record`` or persisted
    state."""
    if record.state is not JobState.RUNNING:
        return LivenessStatus.NOT_APPLICABLE

    if not record.lock_protected:
        return LivenessStatus.UNKNOWN

    lock = FileLock(job_lock_path(root, record.client_slug, record.job_id))
    if lock.try_acquire():
        lock.release()
        return LivenessStatus.STALE
    return LivenessStatus.RUNNING_ACTIVE


__all__ = ["LivenessStatus", "probe_liveness"]
