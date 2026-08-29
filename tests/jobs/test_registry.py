"""Tests for the explicit job operation registry (MKT-11C)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.jobs.models import JobOutcome
from core.jobs.registry import (
    DuplicateOperationError,
    JobRegistry,
    JobRiskClass,
    OperationSpec,
    UnknownOperationError,
    default_registry,
)


class _NoopParams(BaseModel):
    pass


def _noop_handler(ctx, params):
    return JobOutcome.completed()


def _spec(operation: str = "test.op") -> OperationSpec:
    return OperationSpec(
        operation=operation,
        params_model=_NoopParams,
        handler=_noop_handler,
        risk_class=JobRiskClass.LOW,
        description="test op",
    )


def test_register_and_resolve() -> None:
    reg = JobRegistry()
    reg.register(_spec())
    spec = reg.resolve("test.op")
    assert spec.operation == "test.op"


def test_resolve_unknown_raises() -> None:
    reg = JobRegistry()
    with pytest.raises(UnknownOperationError):
        reg.resolve("nope")


def test_duplicate_registration_raises() -> None:
    reg = JobRegistry()
    reg.register(_spec())
    with pytest.raises(DuplicateOperationError):
        reg.register(_spec())


def test_is_registered() -> None:
    reg = JobRegistry()
    assert reg.is_registered("test.op") is False
    reg.register(_spec())
    assert reg.is_registered("test.op") is True


def test_list_operations_stable_order() -> None:
    reg = JobRegistry()
    reg.register(_spec("zeta.op"))
    reg.register(_spec("alpha.op"))
    ops = [s.operation for s in reg.list_operations()]
    assert ops == ["alpha.op", "zeta.op"]


def test_registries_are_isolated() -> None:
    """Two JobRegistry instances never see each other's operations —
    this is what lets tests run without global-state contamination."""
    reg1 = JobRegistry()
    reg2 = JobRegistry()
    reg1.register(_spec())
    assert reg1.is_registered("test.op") is True
    assert reg2.is_registered("test.op") is False


def test_no_dynamic_import_no_eval_surface() -> None:
    """Structural pin: the registry module must not contain any dynamic
    execution primitive."""
    import inspect

    from core.jobs import registry as registry_module

    source = inspect.getsource(registry_module)
    for forbidden in ("importlib", "eval(", "exec(", "__import__"):
        assert forbidden not in source


def test_default_registry_has_demo_operations() -> None:
    for op in ("demo.echo", "demo.fail", "demo.needs_approval"):
        assert default_registry.is_registered(op)


def test_demo_operations_are_dev_only() -> None:
    for op in ("demo.echo", "demo.fail", "demo.needs_approval"):
        spec = default_registry.resolve(op)
        assert spec.dev_only is True


def test_sensitive_param_fields_default_empty() -> None:
    spec = _spec()
    assert spec.sensitive_param_fields == frozenset()
