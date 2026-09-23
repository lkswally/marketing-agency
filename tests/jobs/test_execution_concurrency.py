"""Job-execution-robustness regression tests: same-job concurrency,
different-job concurrency, and the WAITING_APPROVAL / lock-lifecycle
interaction. Audit-chain-specific concurrency (multiple jobs, same
client, writing audit events concurrently) is covered separately in
tests/memory/test_audit_concurrency.py, once per instruction #10 (this
file measures parallelism around the handler, not around the audit
critical section).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from core.application.context import OperationContext
from core.jobs.models import JobOutcome, JobState
from core.jobs.registry import JobRegistry, JobRiskClass, OperationSpec
from core.jobs.runner import InlineJobRunner, JobTransitionError
from core.memory import JsonFileMemory

_CALL_LOG: list[tuple[str, float]] = []
_CALL_LOG_LOCK = threading.Lock()


class _SlowEchoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=500)
    delay_seconds: float = 0.3


def _slow_echo_handler(ctx: OperationContext, params: _SlowEchoParams) -> JobOutcome:
    """Deliberately takes measurable time so concurrent callers actually
    have a window to race, instead of the race depending on unrealistic
    thread-scheduling luck around an instantaneous handler."""
    with _CALL_LOG_LOCK:
        _CALL_LOG.append((f"start:{ctx.client_slug}:{params.message}", time.monotonic()))
    time.sleep(params.delay_seconds)
    with _CALL_LOG_LOCK:
        _CALL_LOG.append((f"end:{ctx.client_slug}:{params.message}", time.monotonic()))
    return JobOutcome.completed(data={"echo": params.message})


def _registry() -> JobRegistry:
    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.slow_echo",
        params_model=_SlowEchoParams,
        handler=_slow_echo_handler,
        risk_class=JobRiskClass.LOW,
        description="Test-only: sleeps briefly, for concurrency tests.",
        dev_only=True,
    ))
    return reg


@pytest.fixture(autouse=True)
def _reset_call_log():
    _CALL_LOG.clear()
    yield
    _CALL_LOG.clear()


# ---------- same job, many concurrent callers ----------


def test_same_job_eight_concurrent_callers_exactly_one_execution(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    reg = _registry()
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=reg)
    ctx = OperationContext(client_slug="acme", root=root)
    record = runner.submit(
        ctx, operation="test.slow_echo",
        params={"message": "hi", "delay_seconds": 0.4},
    )

    results: list[JobState] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            r = runner.run("acme", record.job_id)
            with lock:
                results.append(r.state)
        except JobTransitionError as e:
            with lock:
                errors.append(str(e))
        except Exception as e:  # noqa: BLE001 — a test failure, not swallowed
            with lock:
                errors.append(f"UNEXPECTED {type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    handler_starts = [e for e in _CALL_LOG if e[0].startswith("start:")]
    assert len(handler_starts) == 1, (
        f"expected exactly 1 handler execution, got {len(handler_starts)}: {_CALL_LOG}"
    )
    assert results == [JobState.COMPLETED], (
        f"expected exactly one winning caller to observe COMPLETED, got {results}"
    )
    assert len(errors) == 7, f"expected 7 rejected callers, got {len(errors)}: {errors}"
    for msg in errors:
        assert "already in progress" in msg, msg
        assert "PermissionError" not in msg
        assert "Traceback" not in msg

    final = runner._repo.get("acme", record.job_id)  # noqa: SLF001 — assert final persisted state
    assert final.state is JobState.COMPLETED


# ---------- different jobs run concurrently, not serialized ----------


def test_different_jobs_execute_concurrently_not_serialized(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    reg = _registry()
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=reg)
    ctx = OperationContext(client_slug="acme", root=root)

    jobs = [
        runner.submit(
            ctx, operation="test.slow_echo",
            params={"message": f"job-{i}", "delay_seconds": 0.6},
        )
        for i in range(4)
    ]

    def worker(job_id: str) -> None:
        runner.run("acme", job_id)

    threads = [threading.Thread(target=worker, args=(j.job_id,)) for j in jobs]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    elapsed = time.monotonic() - t0

    # 4 handlers x 0.6s each: fully serialized would take ~2.4s+; running
    # concurrently should finish well under that. The bound (1.8s) is
    # generous relative to true concurrent execution (~0.6-0.9s expected)
    # to absorb thread-startup/system-load jitter under a full-suite run,
    # while staying well clear of the serialized floor so a regression to
    # a de-facto global lock still fails this test.
    assert elapsed < 1.8, (
        f"different jobs took {elapsed:.2f}s — looks serialized, the "
        "per-job lock may have become a global lock"
    )

    starts = sorted(t for name, t in _CALL_LOG if name.startswith("start:"))
    ends = sorted(t for name, t in _CALL_LOG if name.startswith("end:"))
    assert len(starts) == 4
    # Overlap check: at least one job's handler started before another
    # job's handler ended — proves real concurrency, not just "fast
    # sequential".
    assert starts[-1] < ends[0], (
        f"no overlap detected between handler executions: starts={starts} ends={ends}"
    )

    for j in jobs:
        final = runner._repo.get("acme", j.job_id)  # noqa: SLF001
        assert final.state is JobState.COMPLETED


# ---------- WAITING_APPROVAL releases the execution lock ----------


class _NeedsApprovalParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


def _needs_approval_handler(ctx: OperationContext, params: _NeedsApprovalParams) -> JobOutcome:
    return JobOutcome.waiting_approval(reason=params.reason)


def test_waiting_approval_releases_execution_lock(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.needs_approval",
        params_model=_NeedsApprovalParams,
        handler=_needs_approval_handler,
        risk_class=JobRiskClass.LOW,
        description="Test-only.",
        dev_only=True,
        may_wait_for_approval=True,
    ))
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=reg)
    ctx = OperationContext(client_slug="acme", root=root)
    record = runner.submit(ctx, operation="test.needs_approval", params={"reason": "review"})

    result = runner.run("acme", record.job_id)
    assert result.state is JobState.WAITING_APPROVAL

    # The lock represents active execution, not ownership until a human
    # decision — a fresh FileLock on the same path must be immediately
    # acquirable now that run() has returned.
    probe = runner._job_lock("acme", record.job_id)  # noqa: SLF001
    assert probe.try_acquire() is True, (
        "execution lock was not released on a WAITING_APPROVAL outcome"
    )
    probe.release()

    # But the state machine still correctly rejects a second run() —
    # this is the state machine's job, not the lock's. Proves the two
    # mechanisms are independent, per instruction #11.
    with pytest.raises(JobTransitionError):
        runner.run("acme", record.job_id)
