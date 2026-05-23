"""Contract tests for ReturnEnvelope (envelope.v1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.contracts import (
    ArtifactKind,
    ArtifactRef,
    ClaimAudit,
    ClaimAuditItem,
    ContractError,
    ContractErrorCode,
    EnvelopeStatus,
    EvidenceRef,
    MemoryWriteRef,
    ReturnEnvelope,
    validate_envelope,
    validate_envelope_strict,
)
from core.domain.enums import ClaimSeverity, ClaimVerdict

pytestmark = pytest.mark.contract


def _now() -> datetime:
    return datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _minimal_payload() -> dict:
    return {
        "status": "completado",
        "agent": "test-agent",
        "task": "do a thing",
        "produced_at": _now().isoformat(),
    }


# ---------- happy path ----------

def test_minimal_envelope_validates() -> None:
    env = ReturnEnvelope(**_minimal_payload())
    assert env.contract_version == "envelope.v1"
    assert env.status is EnvelopeStatus.COMPLETADO


def test_round_trip_json() -> None:
    original = ReturnEnvelope(
        **_minimal_payload(),
        client_slug="demo-co",
        artifacts=[
            ArtifactRef(
                path="outputs/demo-co/copy.md",
                kind=ArtifactKind.FILE,
                sha256="a" * 64,
                bytes=120,
            )
        ],
        memory_writes=[MemoryWriteRef(topic_key="marketing-agency-os/demo-co/brief", backend="json")],
        notes="ok",
    )
    payload = original.to_json()
    assert json.loads(payload)["contract_version"] == "envelope.v1"
    reloaded = ReturnEnvelope.from_json(payload)
    assert reloaded.model_dump() == original.model_dump()


def test_envelope_with_claims_audit() -> None:
    env = ReturnEnvelope(
        **_minimal_payload(),
        claims_audit=ClaimAudit(
            claims=[
                ClaimAuditItem(
                    claim_id="c1",
                    text="3x faster.",
                    severity=ClaimSeverity.CAVEAT,
                    verdict=ClaimVerdict.PARTIAL,
                    evidence_refs=[EvidenceRef(evidence_id="e1", trust_level=0.8)],
                )
            ],
            overall_severity=ClaimSeverity.CAVEAT,
            overall_verdict=ClaimVerdict.PARTIAL,
        ),
    )
    assert env.claims_audit is not None
    assert env.claims_audit.claims[0].claim_id == "c1"


# ---------- failures ----------

def test_failure_status_requires_blockers_or_notes() -> None:
    with pytest.raises(ValidationError):
        ReturnEnvelope(
            **{**_minimal_payload(), "status": "fallido"}
        )


def test_failure_status_with_blockers_is_ok() -> None:
    ReturnEnvelope(
        **{**_minimal_payload(), "status": "FAIL", "bloqueadores": ["mixed content"]}
    )


def test_failure_status_with_notes_only_is_ok() -> None:
    ReturnEnvelope(
        **{**_minimal_payload(), "status": "fallido", "notes": "timed out"}
    )


# ---------- contract_version pinning ----------

def test_contract_version_wrong_value_rejected() -> None:
    bad = {**_minimal_payload(), "contract_version": "envelope.v2"}
    ok, errs = validate_envelope(bad)
    assert ok is False
    assert any(e.code is ContractErrorCode.VERSION_MISMATCH for e in errs)


# ---------- timezone ----------

def test_naive_produced_at_rejected() -> None:
    payload = {**_minimal_payload(), "produced_at": datetime(2026, 5, 22, 12).isoformat()}
    ok, errs = validate_envelope(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.NAIVE_DATETIME for e in errs)


# ---------- extra field forbidden ----------

def test_extra_field_rejected() -> None:
    payload = {**_minimal_payload(), "rogue_field": "no"}
    ok, errs = validate_envelope(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.EXTRA_FIELD for e in errs)


# ---------- slug ----------

def test_bad_client_slug_rejected() -> None:
    payload = {**_minimal_payload(), "client_slug": "Bad Slug"}
    ok, errs = validate_envelope(payload)
    assert ok is False


def test_reserved_client_slug_rejected() -> None:
    payload = {**_minimal_payload(), "client_slug": "_shared"}
    ok, errs = validate_envelope(payload)
    assert ok is False


# ---------- memory writes ----------

def test_duplicate_topic_keys_rejected() -> None:
    payload = {
        **_minimal_payload(),
        "memory_writes": [
            {"topic_key": "x", "backend": "json"},
            {"topic_key": "x", "backend": "engram"},
        ],
    }
    ok, errs = validate_envelope(payload)
    assert ok is False
    assert any(e.code is ContractErrorCode.DUPLICATE_REF for e in errs)


# ---------- artifacts ----------

def test_artifact_sha256_pattern_enforced() -> None:
    bad = {
        **_minimal_payload(),
        "artifacts": [
            {"path": "x", "kind": "file", "sha256": "not-a-hash"}
        ],
    }
    ok, errs = validate_envelope(bad)
    assert ok is False


def test_artifact_kind_enum_enforced() -> None:
    bad = {
        **_minimal_payload(),
        "artifacts": [{"path": "x", "kind": "carrier-pigeon"}],
    }
    ok, errs = validate_envelope(bad)
    assert ok is False
    assert any(e.code is ContractErrorCode.INVALID_ENUM for e in errs)


# ---------- strict validator ----------

def test_strict_returns_instance_on_valid() -> None:
    env = validate_envelope_strict(_minimal_payload())
    assert isinstance(env, ReturnEnvelope)


def test_strict_raises_on_invalid() -> None:
    with pytest.raises(ContractError) as exc:
        validate_envelope_strict({**_minimal_payload(), "status": "neither"})
    assert exc.value.payload.contract == "envelope.v1"
