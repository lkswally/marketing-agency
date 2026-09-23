"""Isolated, real correctness tests for core.memory.filelock — run and
verified BEFORE this primitive is wired into JobRunner or the audit
writer. See core/memory/filelock.py's module docstring for exactly what
this mechanism does and does not guarantee.

Every test here demonstrates real OS behavior on this machine — none of
it is asserted from documentation alone.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from core.memory.filelock import FileLock, LockTimeoutError

_CHILD_ACQUIRE_AND_HOLD = """
import sys
from pathlib import Path
sys.path.insert(0, {repo_root!r})
from core.memory.filelock import FileLock

lock = FileLock(Path({lock_path!r}))
ok = lock.try_acquire()
print("ACQUIRED" if ok else "FAILED", flush=True)
if ok:
    # Hold it until killed, or until stdin closes (graceful path for cleanup).
    sys.stdin.readline()
"""

REPO_ROOT = str(Path(__file__).resolve().parents[2])


# ---------- A: two threads, independent fds, mutual exclusion ----------


def test_two_threads_cannot_both_acquire_same_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "job_x.lock"
    lock_a = FileLock(lock_path)
    lock_b = FileLock(lock_path)

    assert lock_a.try_acquire() is True
    try:
        # A second, independent FileLock instance (independent fd) on the
        # SAME path, from another thread, must fail to acquire while A
        # holds it.
        results: list[bool] = []

        def attempt() -> None:
            results.append(lock_b.try_acquire())

        t = threading.Thread(target=attempt)
        t.start()
        t.join(timeout=5)
        assert results == [False], (
            "a second thread acquired the same lock while the first thread "
            "still held it"
        )
    finally:
        lock_a.release()

    # Now that A released, B must be able to acquire it.
    assert lock_b.try_acquire() is True
    lock_b.release()


# ---------- B: two independent OS processes, mutual exclusion ----------


def test_two_processes_cannot_both_acquire_same_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "job_proc.lock"
    script = _CHILD_ACQUIRE_AND_HOLD.format(
        repo_root=REPO_ROOT, lock_path=str(lock_path),
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        line = child.stdout.readline().strip()
        assert line == "ACQUIRED", f"child failed to acquire its own fresh lock: {line!r}"

        # Parent (a separate process-level lock instance) must fail while
        # the child process holds the OS lock.
        parent_lock = FileLock(lock_path)
        assert parent_lock.try_acquire() is False, (
            "parent acquired a lock that a live child process holds"
        )
    finally:
        child.stdin.write("go\n")
        child.stdin.flush()
        child.stdin.close()
        child.wait(timeout=5)

    # Child exited cleanly (released the lock) — parent can now acquire it.
    parent_lock = FileLock(lock_path)
    assert parent_lock.try_acquire() is True
    parent_lock.release()


# ---------- C: killing the owning process releases the OS lock ----------


def test_killing_owner_process_releases_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "job_crash.lock"
    script = _CHILD_ACQUIRE_AND_HOLD.format(
        repo_root=REPO_ROOT, lock_path=str(lock_path),
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    line = child.stdout.readline().strip()
    assert line == "ACQUIRED", f"child failed to acquire its own fresh lock: {line!r}"

    other = FileLock(lock_path)
    assert other.try_acquire() is False, "sanity check: lock must be held before the kill"

    # Simulate a crash: no graceful shutdown, no chance to run a `finally`.
    child.kill()
    child.wait(timeout=5)

    # Give the OS a brief moment to finish reclaiming the process's
    # descriptors — not expected to be needed, but avoids flakiness on
    # slower CI/VPS filesystems without weakening the assertion itself.
    deadline = time.monotonic() + 3.0
    acquired = False
    while time.monotonic() < deadline:
        if other.try_acquire():
            acquired = True
            break
        time.sleep(0.05)

    assert acquired, (
        "another holder could not acquire the lock after the owning "
        "process was killed — the OS did not release it on crash"
    )
    other.release()


# ---------- D: locks on different paths never contend ----------


def test_locks_on_different_paths_do_not_block_each_other(tmp_path: Path) -> None:
    lock_1 = FileLock(tmp_path / "job_a.lock")
    lock_2 = FileLock(tmp_path / "job_b.lock")

    assert lock_1.try_acquire() is True
    try:
        assert lock_2.try_acquire() is True, (
            "a lock on an unrelated path was blocked by a lock on a "
            "different path"
        )
        lock_2.release()
    finally:
        lock_1.release()


# ---------- acquire() timeout behavior ----------


def test_acquire_raises_lock_timeout_error_not_a_hang(tmp_path: Path) -> None:
    lock_path = tmp_path / "job_timeout.lock"
    holder = FileLock(lock_path)
    assert holder.try_acquire() is True
    try:
        waiter = FileLock(lock_path)
        start = time.monotonic()
        with pytest.raises(LockTimeoutError):
            waiter.acquire(timeout=0.3, poll_interval=0.05)
        elapsed = time.monotonic() - start
        # Must actually have waited close to the timeout, not returned
        # instantly (proves it polled) and must not have hung well past it.
        assert 0.2 <= elapsed <= 2.0
    finally:
        holder.release()


# ---------- many racing FIRST-TIME openers of a brand-new lock file ----------


def test_many_threads_racing_first_acquire_of_a_fresh_lock_file(tmp_path: Path) -> None:
    """Regression test for a real bug found via tests/jobs/test_execution_concurrency.py:
    several threads all opening the SAME brand-new (zero-byte) lock file
    for the first time simultaneously — each with its own fd — could
    transiently raise PermissionError while preparing the 1-byte
    lockable region on Windows, before _ensure_lockable_region grew a
    retry. Exactly one must win try_acquire(); nobody may raise."""
    lock_path = tmp_path / "brand_new.lock"
    n = 12
    results: list[bool] = []
    errors: list[str] = []
    result_lock = threading.Lock()

    def attempt() -> None:
        try:
            lock = FileLock(lock_path)
            ok = lock.try_acquire()
            with result_lock:
                results.append(ok)
            if ok:
                time.sleep(0.05)
                lock.release()
        except Exception as e:  # noqa: BLE001 — a test failure, not swallowed
            with result_lock:
                errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=attempt) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == [], f"unexpected errors from concurrent first-time acquire: {errors}"
    assert results.count(True) == 1, (
        f"expected exactly 1 winner among {n} racing first-time acquirers, "
        f"got {results.count(True)}: {results}"
    )
    assert results.count(False) == n - 1


def test_acquire_succeeds_once_lock_is_released_before_deadline(tmp_path: Path) -> None:
    lock_path = tmp_path / "job_release_race.lock"
    holder = FileLock(lock_path)
    assert holder.try_acquire() is True

    def release_soon() -> None:
        time.sleep(0.15)
        holder.release()

    threading.Thread(target=release_soon).start()

    waiter = FileLock(lock_path)
    waiter.acquire(timeout=2.0, poll_interval=0.02)  # must not raise
    waiter.release()
