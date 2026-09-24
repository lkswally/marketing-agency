"""Audit-chain concurrency integrity (job-execution-robustness).

Goes beyond verify_chain() alone, per explicit instruction: a bug that
silently DROPS an event could still leave the remaining chain internally
valid. These tests independently check event count, uniqueness, and
prev_hash linkage against what was actually appended, not just that the
surviving chain is self-consistent.
"""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from core.application.context import OperationContext
from core.approval.approval_pack import ApprovalPackBuilder
from core.contracts import AuditEventType, AuditTrailEvent, verify_chain
from core.jobs.models import JobOutcome
from core.jobs.registry import JobRegistry, JobRiskClass, OperationSpec
from core.jobs.runner import InlineJobRunner
from core.memory import JsonFileMemory
from core.memory.filelock import FileLock
from core.pipeline.orchestrator import PipelineOrchestrator


class _EchoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=500)


def _echo_handler(ctx: OperationContext, params: _EchoParams) -> JobOutcome:
    return JobOutcome.completed(data={"echo": params.message})


def _registry() -> JobRegistry:
    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.echo",
        params_model=_EchoParams,
        handler=_echo_handler,
        risk_class=JobRiskClass.LOW,
        description="Test-only.",
        dev_only=True,
    ))
    return reg


def test_two_different_jobs_same_client_concurrent_audit_writes_are_intact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mem"
    reg = _registry()
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=reg)
    ctx = OperationContext(client_slug="acme", root=root)

    n_jobs = 6
    jobs = [
        runner.submit(ctx, operation="test.echo", params={"message": f"m{i}"})
        for i in range(n_jobs)
    ]
    # Each submit() already appended one "submitted" audit event
    # sequentially (single-threaded so far) — count them as a baseline.
    events_after_submit = mem.read_audit_events("acme")
    assert len(events_after_submit) == n_jobs

    errors: list[str] = []

    def worker(job_id: str) -> None:
        try:
            runner.run("acme", job_id)
        except Exception as e:  # noqa: BLE001 — captured, not swallowed
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(j.job_id,)) for j in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert errors == [], f"unexpected errors during concurrent run(): {errors}"

    events = mem.read_audit_events("acme")
    # Each job's run() appends exactly one more event ("started" then
    # "completed" -> 2 events per job) on top of the n_jobs "submitted"
    # events already counted above.
    expected_count = n_jobs + (n_jobs * 2)
    assert len(events) == expected_count, (
        f"expected {expected_count} audit events (no event lost to the "
        f"race), got {len(events)}"
    )

    # No two events share an event_id.
    event_ids = [e.event_id for e in events]
    assert len(set(event_ids)) == len(event_ids), "duplicate event_id found"

    # No two events share a hash (each hash is derived from unique content
    # including event_id, so a collision here would indicate corruption).
    hashes = [e.hash for e in events]
    assert len(set(hashes)) == len(hashes), "duplicate event hash found"

    # Every prev_hash correctly chains to the immediately preceding
    # event's hash, in on-disk order — this is the check that would catch
    # a "chain internally consistent but missing an event" bug that
    # verify_chain() alone, run against a truncated list, would miss.
    for i in range(1, len(events)):
        assert events[i].prev_hash == events[i - 1].hash, (
            f"event {i} (event_id={events[i].event_id}) does not chain to "
            f"the immediately preceding event on disk"
        )
    assert events[0].prev_hash is None

    breaks = verify_chain(events)
    assert breaks == [], f"verify_chain reported breaks at indices: {breaks}"

    # The persisted chain tail must equal the hash of the last event on
    # disk — proves the tail file itself wasn't left pointing at a stale
    # or wrong value by the race.
    assert mem.last_audit_hash("acme") == events[-1].hash


def test_mixed_job_approval_pipeline_writers_same_client_audit_chain_intact(
    tmp_path: Path,
) -> None:
    """GAP 1 (job-execution-robustness follow-up): a job writer, an
    approval writer, and a pipeline writer — the three real, current
    productive callers of the audit trail — all writing concurrently to
    the SAME client's audit chain, all now on append_audit_event_atomic.

    This is the scenario the earlier two-jobs-only test didn't cover:
    different *kinds* of writer, not just different job ids, racing on
    the one lock. Verifies exact event count, no loss, unique hashes,
    an on-disk-contiguous prev_hash chain, verify_chain()==PASS, and
    tail == last event's hash.
    """
    from core.strategy import StrategyPipeline

    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    reg = _registry()
    runner = InlineJobRunner(mem, root=root, registry=reg)

    demo_brief = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "clients"
        / "demo-saas"
        / "brief.json"
    )
    report = StrategyPipeline(memory=mem).run_from_path(demo_brief).report
    client_slug = report.client_slug
    ctx = OperationContext(client_slug=client_slug, root=root)
    baseline_count = len(mem.read_audit_events(client_slug))

    n_job_writers = 4
    n_approval_writers = 4
    n_pipeline_writers = 4

    jobs = [
        runner.submit(ctx, operation="test.echo", params={"message": f"m{i}"})
        for i in range(n_job_writers)
    ]
    events_after_submit = mem.read_audit_events(client_slug)
    assert len(events_after_submit) == baseline_count + n_job_writers

    errors: list[str] = []
    lock = threading.Lock()

    def record_error(exc: Exception) -> None:
        with lock:
            errors.append(f"{type(exc).__name__}: {exc}")

    def job_worker(job_id: str) -> None:
        try:
            runner.run(client_slug, job_id)
        except Exception as e:  # noqa: BLE001 — captured, not swallowed
            record_error(e)

    def approval_worker(i: int) -> None:
        try:
            builder = ApprovalPackBuilder(mem)
            pack = builder.build_from_report(report)
            builder.persist(pack)
        except Exception as e:  # noqa: BLE001
            record_error(e)

    def pipeline_worker(i: int) -> None:
        try:
            orch = PipelineOrchestrator(mem, outputs_root=tmp_path / "outputs")
            orch._emit_event(  # noqa: SLF001 — exercising the real writer directly
                client_slug=client_slug,
                payload={"note": f"pipeline-writer-{i}"},
            )
        except Exception as e:  # noqa: BLE001
            record_error(e)

    threads = (
        [threading.Thread(target=job_worker, args=(j.job_id,)) for j in jobs]
        + [threading.Thread(target=approval_worker, args=(i,)) for i in range(n_approval_writers)]
        + [threading.Thread(target=pipeline_worker, args=(i,)) for i in range(n_pipeline_writers)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert errors == [], f"unexpected errors during mixed concurrent writes: {errors}"

    events = mem.read_audit_events(client_slug)
    # n_job_writers "submitted" (already counted) + 2 per job run
    # ("started" + "completed") + 1 per approval persist + 1 per
    # pipeline emit.
    expected_count = (
        baseline_count
        + n_job_writers
        + (n_job_writers * 2)
        + n_approval_writers
        + n_pipeline_writers
    )
    assert len(events) == expected_count, (
        f"expected {expected_count} audit events (no event lost to the "
        f"mixed-writer race), got {len(events)}"
    )

    event_ids = [e.event_id for e in events]
    assert len(set(event_ids)) == len(event_ids), "duplicate event_id found"

    hashes = [e.hash for e in events]
    assert len(set(hashes)) == len(hashes), "duplicate event hash found"

    for i in range(1, len(events)):
        assert events[i].prev_hash == events[i - 1].hash, (
            f"event {i} (event_id={events[i].event_id}) does not chain to "
            f"the immediately preceding event on disk"
        )
    assert events[0].prev_hash is None

    breaks = verify_chain(events)
    assert breaks == [], f"verify_chain reported breaks at indices: {breaks}"

    assert mem.last_audit_hash(client_slug) == events[-1].hash


def test_audit_lock_path_is_separate_from_any_job_lock(tmp_path: Path) -> None:
    """Sanity/documentation check: the audit lock and a job's execution
    lock are different files, so holding one never blocks the other."""
    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    audit_lock = FileLock(mem._audit_lock_path("acme"))  # noqa: SLF001
    job_lock = FileLock(root / "acme" / "_locks" / "job_some-job-id.lock")

    assert audit_lock.path != job_lock.path
    assert audit_lock.try_acquire() is True
    try:
        assert job_lock.try_acquire() is True
        job_lock.release()
    finally:
        audit_lock.release()


def test_manually_building_two_events_with_the_same_stale_prev_hash_is_rejected(
    tmp_path: Path,
) -> None:
    """Direct proof that append_audit_event (the non-atomic path, still
    used by other callers) fails loudly rather than corrupting the chain
    when handed a stale prev_hash — the exact scenario a caller computing
    prev_hash outside the lock could hit under concurrency."""
    from core.domain.base import utcnow
    from core.memory.errors import AuditChainError

    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    first = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE, actor="t", occurred_at=utcnow(),
        client_slug="acme", payload={"n": 1}, prev_hash=None,
    )
    mem.append_audit_event(first)

    # Both events built against the SAME (now stale) prev_hash, simulating
    # two callers that both read the tail before either appended.
    stale_prev = None
    second = AuditTrailEvent.build(
        event_type=AuditEventType.NOTE, actor="t", occurred_at=utcnow(),
        client_slug="acme", payload={"n": 2}, prev_hash=stale_prev,
    )
    try:
        mem.append_audit_event(second)
        raised = False
    except AuditChainError:
        raised = True
    assert raised, "a stale prev_hash was silently accepted instead of rejected"
