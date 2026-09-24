"""RUNNING-state / audit persistence ordering (job-execution-robustness,
GAP 2 follow-up).

Invariant under test: the handler must NEVER run unless RUNNING,
started_at and lock_protected have already been durably persisted, AND
the "started" audit event has already been durably written. Each test
here deliberately injects a failure at one of the two durability steps
(or simulates a process death between them) and proves the handler never
executes, and that the resulting on-disk state fails closed rather than
silently proceeding.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from core.application.context import OperationContext
from core.jobs.liveness import LivenessStatus, probe_liveness
from core.jobs.models import JobOutcome, JobState
from core.jobs.registry import JobRegistry, JobRiskClass, OperationSpec
from core.jobs.repository import JobRepository
from core.jobs.runner import InlineJobRunner, JobStartError
from core.memory import JsonFileMemory

REPO_ROOT = str(Path(__file__).resolve().parents[2])


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=200)


_HANDLER_CALLS: list[str] = []


def _counting_handler(ctx: OperationContext, params: _Params) -> JobOutcome:
    _HANDLER_CALLS.append(params.message)
    return JobOutcome.completed(data={"echo": params.message})


def _registry() -> JobRegistry:
    reg = JobRegistry()
    reg.register(OperationSpec(
        operation="test.count",
        params_model=_Params,
        handler=_counting_handler,
        risk_class=JobRiskClass.LOW,
        description="Test-only.",
        dev_only=True,
    ))
    return reg


@pytest.fixture(autouse=True)
def _reset_handler_calls():
    _HANDLER_CALLS.clear()
    yield
    _HANDLER_CALLS.clear()


# ---------- scenario (a): save(RUNNING) fails ----------

def test_save_running_failure_leaves_job_queued_and_handler_never_runs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=_registry())
    ctx = OperationContext(client_slug="acme", root=root)
    record = runner.submit(ctx, operation="test.count", params={"message": "x"})

    real_save = runner._repo.save  # noqa: SLF001 — deliberate fault injection
    calls = {"n": 0}

    def _failing_save(rec):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated disk failure on RUNNING persist")
        return real_save(rec)

    runner._repo.save = _failing_save  # noqa: SLF001

    with pytest.raises(JobStartError):
        runner.run("acme", record.job_id)

    assert _HANDLER_CALLS == [], "handler must never run when persisting RUNNING fails"

    # The atomic write never landed — on-disk record is untouched: QUEUED.
    on_disk = JobRepository(mem).get("acme", record.job_id)
    assert on_disk.state is JobState.QUEUED
    assert on_disk.lock_protected is False

    # The lock was released (run()'s finally) — a fresh attempt (with the
    # fault removed) can retry cleanly, proving nothing was left wedged.
    runner._repo.save = real_save  # noqa: SLF001
    completed = runner.run("acme", record.job_id)
    assert completed.state is JobState.COMPLETED
    assert _HANDLER_CALLS == ["x"]


# ---------- scenario (b): the "started" audit write fails ----------

def test_audit_started_failure_leaves_running_persisted_but_handler_never_runs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    runner = InlineJobRunner(mem, root=root, registry=_registry())
    ctx = OperationContext(client_slug="acme", root=root)
    record = runner.submit(ctx, operation="test.count", params={"message": "y"})

    real_atomic = mem.append_audit_event_atomic
    calls = {"n": 0}

    def _failing_atomic(client_slug, build_event):
        calls["n"] += 1
        # First atomic audit call after submit() is the "started" event.
        if calls["n"] == 1:
            raise OSError("simulated audit-chain write failure on 'started'")
        return real_atomic(client_slug, build_event)

    mem.append_audit_event_atomic = _failing_atomic

    with pytest.raises(JobStartError):
        runner.run("acme", record.job_id)

    assert _HANDLER_CALLS == [], "handler must never run when the 'started' audit write fails"

    # RUNNING + lock_protected WAS already durably persisted (step 2
    # completed before step 3 failed) — this is the documented, accepted
    # non-transactional gap: no rollback of the JobRecord write.
    mem.append_audit_event_atomic = real_atomic  # restore before reading back
    on_disk = JobRepository(mem).get("acme", record.job_id)
    assert on_disk.state is JobState.RUNNING
    assert on_disk.lock_protected is True

    # The execution lock was released (finally) — liveness now correctly
    # reads this as STALE, not a mystery. No new job state was invented;
    # this is exactly the liveness mechanism this milestone already built.
    assert probe_liveness(root, on_disk) is LivenessStatus.STALE


# ---------- scenario (c): the process dies between save(RUNNING) and the audit write ----------

_CHILD_DIE_BETWEEN_SAVE_AND_AUDIT = """
import os
import sys
sys.path.insert(0, {repo_root!r})
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from core.application.context import OperationContext
from core.jobs.models import JobOutcome
from core.jobs.registry import JobRegistry, JobRiskClass, OperationSpec
from core.jobs.runner import InlineJobRunner
from core.memory import JsonFileMemory

class P(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=200)

_calls = []

def _handler(ctx, params):
    _calls.append(params.message)
    return JobOutcome.completed(data={{}})

reg = JobRegistry()
reg.register(OperationSpec(
    operation="test.count", params_model=P, handler=_handler,
    risk_class=JobRiskClass.LOW, description="test-only", dev_only=True,
))
root = Path({root!r})
mem = JsonFileMemory(root)
runner = InlineJobRunner(mem, root=root, registry=reg)
ctx = OperationContext(client_slug="acme", root=root)
record = runner.submit(ctx, operation="test.count", params={{"message": "z"}})
print(f"JOB_ID:{{record.job_id}}", flush=True)

real_audit = runner._audit

def _die_instead_of_audit(record, *, action, from_state):
    # RUNNING has already been persisted by _begin_running at this point
    # (save() happens before _audit() is called) — simulate the process
    # dying in the gap between that persist and the audit write actually
    # landing, before the handler is ever reached.
    sys.stdout.flush()
    os._exit(9)

runner._audit = _die_instead_of_audit
runner.run("acme", record.job_id)
"""


def test_process_dies_between_save_and_audit_write_handler_never_ran(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mem"
    script = _CHILD_DIE_BETWEEN_SAVE_AND_AUDIT.format(repo_root=REPO_ROOT, root=str(root))
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    job_id = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        line = child.stdout.readline().strip()
        if line.startswith("JOB_ID:"):
            job_id = line.split(":", 1)[1]
            break
    child.wait(timeout=10)
    assert job_id is not None, "child never reported a job_id"
    assert child.returncode == 9, f"child did not die as expected: rc={child.returncode}"

    mem = JsonFileMemory(root)
    on_disk = JobRepository(mem).get("acme", job_id)

    # RUNNING + lock_protected were persisted before the simulated death —
    # the handler itself never had a chance to run (it's only invoked
    # after _begin_running returns, which the child died inside of).
    assert on_disk.state is JobState.RUNNING
    assert on_disk.lock_protected is True
    assert on_disk.result_data is None
    assert on_disk.finished_at is None

    # The OS released the lock the instant the process exited — liveness
    # correctly reads this as STALE, identical to scenario (b). The
    # mechanism does not need to know *why* the audit write never landed.
    deadline = time.monotonic() + 3.0
    status = None
    while time.monotonic() < deadline:
        status = probe_liveness(root, on_disk)
        if status is LivenessStatus.STALE:
            break
        time.sleep(0.05)
    assert status is LivenessStatus.STALE
