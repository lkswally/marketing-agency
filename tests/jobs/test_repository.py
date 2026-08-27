"""Tests for job persistence — no singleton, full history, multi-tenant
isolation, corruption tolerance, params sanitization (MKT-11C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.jobs.models import JOB_KIND, JobRecord, JobState
from core.jobs.repository import JobPersistenceError, JobRepository, sanitize_params
from core.memory import EntityNotFound, JsonFileMemory


def _repo(tmp_path: Path) -> JobRepository:
    return JobRepository(JsonFileMemory(tmp_path / "mem"))


def _record(client: str = "acme", **kwargs) -> JobRecord:
    return JobRecord(client_slug=client, operation="demo.echo", **kwargs)


# ---------- save / get ----------

def test_save_and_get_round_trip(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    record = _record()
    repo.save(record)
    loaded = repo.get("acme", record.job_id)
    assert loaded.job_id == record.job_id
    assert loaded.state is JobState.QUEUED


def test_get_missing_raises_entity_not_found(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(EntityNotFound):
        repo.get("acme", "does-not-exist")


def test_no_singleton_id_used(tmp_path: Path) -> None:
    """Two jobs for the same client must not collide — each gets its own
    file, unlike the approval_pack 'current' singleton pattern."""
    repo = _repo(tmp_path)
    r1 = _record()
    r2 = _record()
    repo.save(r1)
    repo.save(r2)
    assert repo.get("acme", r1.job_id).job_id == r1.job_id
    assert repo.get("acme", r2.job_id).job_id == r2.job_id
    assert r1.job_id != r2.job_id


def test_history_preserved_across_saves(tmp_path: Path) -> None:
    """Re-saving the SAME job_id (a state transition) does not touch any
    other job's file."""
    repo = _repo(tmp_path)
    r1 = _record()
    r2 = _record()
    repo.save(r1)
    repo.save(r2)
    r1.state = JobState.RUNNING
    repo.save(r1)
    assert repo.get("acme", r1.job_id).state is JobState.RUNNING
    assert repo.get("acme", r2.job_id).state is JobState.QUEUED  # untouched


# ---------- multi-tenant isolation ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    acme_job = _record("acme")
    other_job = _record("other-client")
    repo.save(acme_job)
    repo.save(other_job)
    with pytest.raises(EntityNotFound):
        repo.get("other-client", acme_job.job_id)
    assert repo.get("acme", acme_job.job_id).client_slug == "acme"


def test_list_for_client_does_not_leak_other_tenants(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save(_record("acme"))
    repo.save(_record("other-client"))
    acme_jobs = repo.list_for_client("acme")
    assert len(acme_jobs) == 1
    assert acme_jobs[0].client_slug == "acme"


# ---------- list_for_client ----------

def test_list_sorted_newest_first(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    repo = _repo(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    r1 = _record(created_at=base)
    r2 = _record(created_at=base + timedelta(hours=1))
    r3 = _record(created_at=base + timedelta(hours=2))
    for r in (r1, r2, r3):
        repo.save(r)
    jobs = repo.list_for_client("acme")
    assert [j.job_id for j in jobs] == [r3.job_id, r2.job_id, r1.job_id]


def test_list_filters_by_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save(_record(state=JobState.QUEUED))
    repo.save(_record(state=JobState.COMPLETED))
    queued = repo.list_for_client("acme", state="queued")
    assert len(queued) == 1
    assert queued[0].state is JobState.QUEUED


def test_list_filters_by_operation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    r1 = JobRecord(client_slug="acme", operation="demo.echo")
    r2 = JobRecord(client_slug="acme", operation="demo.fail")
    repo.save(r1)
    repo.save(r2)
    echoes = repo.list_for_client("acme", operation="demo.echo")
    assert len(echoes) == 1
    assert echoes[0].job_id == r1.job_id


def test_list_respects_limit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for _ in range(5):
        repo.save(_record())
    assert len(repo.list_for_client("acme", limit=2)) == 2


def test_list_empty_when_no_jobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.list_for_client("acme") == []


# ---------- corrupted / invalid persistence ----------

def test_get_corrupted_json_raises_persistence_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    record = _record()
    repo.save(record)
    path = tmp_path / "mem" / "acme" / JOB_KIND / f"{record.job_id}.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(JobPersistenceError):
        repo.get("acme", record.job_id)


def test_get_schema_mismatch_raises_persistence_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    record = _record()
    repo.save(record)
    path = tmp_path / "mem" / "acme" / JOB_KIND / f"{record.job_id}.json"
    path.write_text('{"totally": "wrong shape"}', encoding="utf-8")
    with pytest.raises(JobPersistenceError):
        repo.get("acme", record.job_id)


def test_list_raises_persistence_error_on_corrupted_json(tmp_path: Path) -> None:
    """Honest limitation: Memory.list() bulk-reads every file for a kind
    in one pass with no per-file recovery point, so a syntactically
    corrupted file fails the WHOLE listing (raised, never an unhandled
    traceback) rather than being silently skipped."""
    repo = _repo(tmp_path)
    good = _record()
    repo.save(good)
    bad = _record()
    repo.save(bad)
    path = tmp_path / "mem" / "acme" / JOB_KIND / f"{bad.job_id}.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(JobPersistenceError):
        repo.list_for_client("acme")


def test_list_skips_schema_mismatched_entries_without_crashing(tmp_path: Path) -> None:
    """A file that IS valid JSON but does not match JobRecord's schema is
    skipped per-entry — that failure happens after the bulk read already
    succeeded, so each record can be validated independently."""
    repo = _repo(tmp_path)
    good = _record()
    repo.save(good)
    bad = _record()
    repo.save(bad)
    path = tmp_path / "mem" / "acme" / JOB_KIND / f"{bad.job_id}.json"
    path.write_text('{"totally": "wrong shape"}', encoding="utf-8")
    jobs = repo.list_for_client("acme")
    assert [j.job_id for j in jobs] == [good.job_id]


# ---------- sanitize_params ----------

def test_sanitize_params_no_sensitive_fields_unchanged() -> None:
    params = {"message": "hi", "count": 3}
    assert sanitize_params(params, frozenset()) == params


def test_sanitize_params_redacts_declared_fields() -> None:
    params = {"message": "hi", "api_key": "sk-secret"}
    result = sanitize_params(params, frozenset({"api_key"}))
    assert result["message"] == "hi"
    assert result["api_key"] == "***redacted***"
    assert "sk-secret" not in result.values()


def test_sanitize_params_missing_field_no_error() -> None:
    params = {"message": "hi"}
    result = sanitize_params(params, frozenset({"api_key"}))
    assert result == {"message": "hi"}


def test_sanitize_params_returns_new_dict_not_mutating_input() -> None:
    params = {"token": "secret"}
    result = sanitize_params(params, frozenset({"token"}))
    assert params["token"] == "secret"  # original untouched
    assert result["token"] == "***redacted***"
