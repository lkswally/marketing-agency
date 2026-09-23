"""Stale-RUNNING liveness detection (job-execution-robustness).

No auto-resume, no auto-mutation of job state — every assertion here
checks that the job record itself is left exactly as observed; only the
derived, never-persisted liveness value is examined.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from core.application.context import OperationContext
from core.jobs.liveness import LivenessStatus, probe_liveness
from core.jobs.models import JobState
from core.jobs.repository import JobRepository
from core.memory import JsonFileMemory

REPO_ROOT = str(Path(__file__).resolve().parents[2])

# Submits a job, then runs it in a way that hangs mid-handler (so the
# record is left RUNNING when this child is killed) — simulating a real
# crash, not a clean shutdown.
_CHILD_SUBMIT_AND_HANG = """
import sys
sys.path.insert(0, {repo_root!r})
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from core.application.context import OperationContext
from core.jobs.models import JobOutcome
from core.jobs.registry import JobRegistry, JobRiskClass, OperationSpec
from core.jobs.runner import InlineJobRunner
from core.memory import JsonFileMemory

class HangParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=200)

def _hang_handler(ctx, params):
    print("RUNNING_NOW", flush=True)
    import time
    time.sleep(60)  # never returns — the parent kills us first
    return JobOutcome.completed(data={{}})

reg = JobRegistry()
reg.register(OperationSpec(
    operation="test.hang", params_model=HangParams, handler=_hang_handler,
    risk_class=JobRiskClass.LOW, description="test-only", dev_only=True,
))
root = Path({root!r})
mem = JsonFileMemory(root)
runner = InlineJobRunner(mem, root=root, registry=reg)
ctx = OperationContext(client_slug="acme", root=root)
record = runner.submit(ctx, operation="test.hang", params={{"message": "hi"}})
print(f"JOB_ID:{{record.job_id}}", flush=True)
runner.run("acme", record.job_id)
"""


def test_not_applicable_for_non_running_states(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    mem = JsonFileMemory(root)
    ctx = OperationContext(client_slug="acme", root=root)
    from core.jobs.runner import InlineJobRunner

    runner = InlineJobRunner(mem, root=root)
    record = runner.submit(ctx, operation="demo.echo", params={"message": "hi"})
    assert probe_liveness(root, record) is LivenessStatus.NOT_APPLICABLE  # QUEUED

    runner.run("acme", record.job_id)
    completed = JobRepository(mem).get("acme", record.job_id)
    assert completed.state is JobState.COMPLETED
    assert probe_liveness(root, completed) is LivenessStatus.NOT_APPLICABLE


def test_legacy_running_without_lock_protected_flag_is_unknown(tmp_path: Path) -> None:
    """A RUNNING record with lock_protected=False (as every record
    persisted before this milestone has, since the field defaults to
    False) must be reported UNKNOWN — never guessed as stale or active."""
    from core.domain.base import new_id, utcnow
    from core.jobs.models import JobRecord

    root = tmp_path / "mem"
    legacy = JobRecord(
        client_slug="acme",
        operation="demo.echo",
        state=JobState.RUNNING,
        started_at=utcnow(),
        job_id=new_id(),
        lock_protected=False,  # explicit, though it's the default
    )
    # No lock file exists for this job at all — exactly the pre-milestone
    # situation. The signal used must not be "does the file exist".
    assert probe_liveness(root, legacy) is LivenessStatus.UNKNOWN


def test_running_active_while_a_real_process_holds_the_lock(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    script = _CHILD_SUBMIT_AND_HANG.format(repo_root=REPO_ROOT, root=str(root))
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        job_id = None
        # Read stdout lines until we see the job_id and confirmation the
        # handler actually started (i.e. the lock is genuinely held).
        deadline = time.monotonic() + 10
        saw_running = False
        while time.monotonic() < deadline:
            line = child.stdout.readline().strip()
            if line.startswith("JOB_ID:"):
                job_id = line.split(":", 1)[1]
            elif line == "RUNNING_NOW":
                saw_running = True
                break
        assert job_id is not None and saw_running, "child never reached RUNNING"

        mem = JsonFileMemory(root)
        record = JobRepository(mem).get("acme", job_id)
        assert record.state is JobState.RUNNING
        assert record.lock_protected is True
        assert probe_liveness(root, record) is LivenessStatus.RUNNING_ACTIVE
    finally:
        child.kill()
        child.wait(timeout=5)


def test_stale_after_owning_process_is_killed(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    script = _CHILD_SUBMIT_AND_HANG.format(repo_root=REPO_ROOT, root=str(root))
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
        elif line == "RUNNING_NOW":
            break
    assert job_id is not None

    mem = JsonFileMemory(root)
    record = JobRepository(mem).get("acme", job_id)
    assert record.state is JobState.RUNNING  # confirmed RUNNING before the kill

    # Simulate a crash: no graceful shutdown, no chance for `finally` to
    # release anything — this is the whole point of using an OS lock.
    child.kill()
    child.wait(timeout=5)

    # The persisted record is untouched by the kill — still RUNNING.
    # No auto-mutation happens anywhere in this module.
    still_running_on_disk = JobRepository(mem).get("acme", job_id)
    assert still_running_on_disk.state is JobState.RUNNING

    deadline = time.monotonic() + 3.0
    status = None
    while time.monotonic() < deadline:
        status = probe_liveness(root, still_running_on_disk)
        if status is LivenessStatus.STALE:
            break
        time.sleep(0.05)
    assert status is LivenessStatus.STALE

    # Re-fetching the record after the probe: still RUNNING, still
    # untouched — probing is read-only, full stop.
    after_probe = JobRepository(mem).get("acme", job_id)
    assert after_probe.state is JobState.RUNNING
