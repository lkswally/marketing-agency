"""Centralized exit-code mapping (MKT-11B).

Before this module, every CLI command mapped every application-service
error to a single generic exit code (``2``) — see
``docs/MKT-11A-Application-Services-Inventory.md`` §6. MKT-11B introduces
the first differentiated table, scoped to the approval-operations
commands (``mkt approvals list/show``, ``mkt approve``, ``mkt reject``).

**This mapping is additive, not retroactive** — ``mkt seo-report`` (and
every other pre-11B command) keeps its existing ``0 / 2`` behaviour
unchanged. Only commands built or touched from MKT-11B onward consume
:func:`exit_code_for`.
"""

from __future__ import annotations

from enum import IntEnum

from .result import ErrorCode


class ExitCode(IntEnum):
    """Stable, documented exit-code vocabulary for approval-operations
    commands. Values are process exit codes — keep them in ``[0, 255]``
    and never reassign a value once shipped."""

    OK = 0
    INVALID_INPUT = 2
    NOT_FOUND = 3
    INVALID_STATE_TRANSITION = 4
    PERMISSION_DENIED = 5
    PERSISTENCE_ERROR = 6
    JOB_FAILED = 7
    """A job reached JobState.FAILED (MKT-11C) — a known, structured
    outcome, not a CLI-adapter error. Distinct from UNEXPECTED: the job
    system worked correctly and the *operation* failed."""
    UNEXPECTED = 70
    """Matches the BSD/sysexits.h ``EX_SOFTWARE`` convention — an
    unexpected internal failure, as opposed to a well-understood,
    user-facing error condition (codes 2–7). Reserved exclusively for
    that — a failed job is JOB_FAILED (7), never 70."""


_ERROR_CODE_TO_EXIT_CODE: dict[ErrorCode, ExitCode] = {
    ErrorCode.INVALID_INPUT: ExitCode.INVALID_INPUT,
    ErrorCode.UNKNOWN_OPERATION: ExitCode.INVALID_INPUT,
    ErrorCode.NOT_FOUND: ExitCode.NOT_FOUND,
    ErrorCode.INVALID_STATE_TRANSITION: ExitCode.INVALID_STATE_TRANSITION,
    ErrorCode.PERMISSION_DENIED: ExitCode.PERMISSION_DENIED,
    ErrorCode.PERSISTENCE_ERROR: ExitCode.PERSISTENCE_ERROR,
    ErrorCode.ALREADY_EXISTS: ExitCode.INVALID_INPUT,
    ErrorCode.PATH_NOT_ALLOWED: ExitCode.INVALID_INPUT,
    ErrorCode.INTERNAL: ExitCode.UNEXPECTED,
}


def exit_code_for(error_code: ErrorCode) -> int:
    """Map an :class:`ErrorCode` to its documented process exit code.

    Falls back to :data:`ExitCode.UNEXPECTED` for any :class:`ErrorCode`
    value added later without an explicit mapping entry — a missing
    mapping is a bug to fix, not a reason to crash the CLI.
    """
    return int(_ERROR_CODE_TO_EXIT_CODE.get(error_code, ExitCode.UNEXPECTED))


__all__ = ["ExitCode", "exit_code_for"]
