"""Cross-platform, single-host advisory file locking.

**What this provides:** mutual exclusion between callers on the SAME host
sharing the SAME local filesystem — threads within one process, and
separate OS processes on that host. The lock is held by the OS against an
open file descriptor; it is released automatically when that descriptor
closes, including on process crash/kill (the OS reclaims file descriptors
unconditionally on process exit).

**What this does NOT provide, and never claims to:**

- Safety across a shared network filesystem (NFS, SMB, ...) — advisory
  locking semantics on network filesystems are notoriously
  implementation-dependent and are NOT exercised or verified by the tests
  in this module. Do not deploy this across hosts sharing storage without
  independently verifying it there first.
- Safety across multiple hosts with no shared filesystem at all — there is
  nothing here to coordinate through in that case.
- Fairness or ordering guarantees among waiters.

Two acquisition modes:

- :meth:`FileLock.try_acquire` — a single non-blocking attempt. Returns
  ``False`` immediately if another holder has it. Used where a second
  concurrent caller must be rejected outright (job execution).
- :meth:`FileLock.acquire` — polls :meth:`try_acquire` against a monotonic
  deadline with a short sleep between attempts. Cross-platform on purpose:
  ``fcntl`` and ``msvcrt`` do not expose the same blocking/timeout
  semantics, so a real blocking wait would behave differently on the two
  platforms. Raises :class:`LockTimeoutError` on timeout — never hangs
  indefinitely, never leaks a raw ``OSError``/``PermissionError`` to the
  caller. Used where a brief wait is acceptable and preferable to an
  outright rejection (the audit-chain critical section).

Windows note (``msvcrt.locking``): it locks a byte range starting at the
file's CURRENT position, and the platform requires that range to actually
exist in the file — locking on an empty file is not reliable across
platforms, so :func:`_acquire_os_lock` writes one reserved byte the first
time the file is empty, and always ``seek(0)`` immediately before every
lock/unlock call so both platforms operate on the same, well-defined
1-byte region regardless of any other activity on the descriptor.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_LOCK_REGION_SIZE = 1


class LockTimeoutError(RuntimeError):
    """Raised by :meth:`FileLock.acquire` when the lock is not obtained
    before the deadline. Never a raw ``OSError``/``PermissionError``."""

    def __init__(self, path: Path, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        super().__init__(
            f"could not acquire lock {path} within {timeout}s "
            "(another holder has it)"
        )


class LockInfrastructureError(RuntimeError):
    """Raised when the lock file/directory itself cannot be created or
    opened (permissions, missing parent that can't be created, disk full,
    ...) — distinct from :class:`LockTimeoutError`, which means the lock
    mechanism worked and another holder legitimately has it. This class
    means the mechanism itself failed. Both fail closed: neither is ever
    mistaken for a successful acquisition by any caller of this module."""


def _ensure_lockable_region(fd: int) -> None:
    """Make sure the file has at least one byte, so locking a 1-byte
    region starting at offset 0 is well-defined on every platform this
    module supports. Idempotent and safe if called concurrently by
    multiple racing openers — worst case, the same single null byte is
    written more than once."""
    size = os.fstat(fd).st_size
    if size < _LOCK_REGION_SIZE:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"\0" * _LOCK_REGION_SIZE)
    os.lseek(fd, 0, os.SEEK_SET)


def _try_lock_fd(fd: int) -> bool:
    """One non-blocking attempt to exclusively lock ``fd``'s 1-byte
    region. Returns True on success, False if already held by someone
    else. Never raises for the ordinary "already locked" case."""
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, _LOCK_REGION_SIZE)
        except OSError:
            return False
        return True
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True


def _unlock_fd(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_REGION_SIZE)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class FileLock:
    """One advisory lock bound to a single path. Not reentrant — a second
    ``try_acquire``/``acquire`` on the same live instance while it already
    holds the lock is not a supported use (create a second instance to
    test contention, as the isolated lock tests do)."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        return self._path

    def try_acquire(self) -> bool:
        """Single non-blocking attempt. Returns False if another holder
        (thread or process, same host) has it. Raises
        :class:`LockInfrastructureError` if the lock file/directory itself
        could not be created or opened — that failure is never
        interpreted as "lock acquired"."""
        if self._fd is not None:
            raise RuntimeError(f"FileLock({self._path}) is already held by this instance")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR)
        except OSError as e:
            raise LockInfrastructureError(
                f"could not create/open lock file {self._path}: {e}"
            ) from e
        try:
            _ensure_lockable_region(fd)
        except OSError as e:
            os.close(fd)
            raise LockInfrastructureError(
                f"could not prepare lock region for {self._path}: {e}"
            ) from e
        if not _try_lock_fd(fd):
            os.close(fd)
            return False
        self._fd = fd
        return True

    def acquire(self, *, timeout: float, poll_interval: float = 0.05) -> None:
        """Poll :meth:`try_acquire` against a monotonic deadline. Raises
        :class:`LockTimeoutError` on timeout, never hangs indefinitely."""
        deadline = time.monotonic() + timeout
        while True:
            if self.try_acquire():
                return
            if time.monotonic() >= deadline:
                raise LockTimeoutError(self._path, timeout)
            time.sleep(poll_interval)

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            _unlock_fd(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> FileLock:
        self.acquire(timeout=10.0)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


__all__ = [
    "FileLock",
    "LockInfrastructureError",
    "LockTimeoutError",
]
