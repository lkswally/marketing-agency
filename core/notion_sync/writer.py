"""NotionWriter abstraction (MKT-5B) — opt-in write path.

Three writers ship in this block, all with identical signatures:

- :class:`RefusingNotionWriter` — safe default. Every call raises
  :class:`NoNotionCredentialsError`. The executor catches it and
  records the task as "skipped: writer refused". This is what gets
  wired when ``--write --confirm`` is requested but
  ``NOTION_TOKEN`` / ``NOTION_TASKS_DATABASE_ID`` are absent OR
  when the operator stays in ``--dry-run``.

- :class:`ScriptedNotionWriter` — test-only. Returns canned
  ``page_id``s keyed by the page properties (so tests can map a
  task to a specific response without depending on call order).

- :class:`NotionClientWriter` — real one, lazy-imports
  ``notion_client``. Constructed only when the operator passes
  ``--write --confirm`` AND both env vars are set. If the SDK
  isn't installed, the constructor raises
  :class:`NoNotionCredentialsError` and the CLI falls back to
  dry-run with a clear warning.

Cardinal safety guarantees:

- The token is read ONCE at construction time, passed to the SDK
  client, and never stored as a long-lived attribute on the
  writer (the SDK client holds it).
- ``__repr__`` redacts the token.
- Errors raised by the SDK are wrapped in
  :class:`NotionWriteError` with a sanitised message — never the
  raw token or the prompt.
- A single attempt per call. No retries (deferred to P-5B.x).
- ``create_page`` only — no ``update_page``, no ``delete_page``,
  no ``archive_page``. Idempotency is enforced at the executor
  level via a memory-resident task_id → page_id map.
- No ``databases.create``; this writer ONLY creates pages in an
  EXISTING database the operator pinned via env var.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

_REDACTED = "***redacted***"
_TOKEN_ENV = "NOTION_TOKEN"
_DATABASE_ID_ENV = "NOTION_TASKS_DATABASE_ID"
_MAX_ERROR_LEN = 200


class NotionWriteError(RuntimeError):  # noqa: N818
    """Wraps every failure from a real Notion call. The executor
    catches this and records the task as ``failed``. The CLI never
    sees the raw SDK exception."""


class NoNotionCredentialsError(NotionWriteError):
    """Raised at writer construction time when:

    - ``NOTION_TOKEN`` is missing, OR
    - ``NOTION_TASKS_DATABASE_ID`` is missing, OR
    - the ``notion-client`` package is not installed.

    Same fallback contract as MKT-4B's ``NoCredentialsError``:
    the CLI catches it and degrades cleanly to dry-run.
    """


@dataclass(frozen=True)
class NotionWriteResult:
    """What a writer returns after a successful create_page call."""

    page_id: str
    request_id: str | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class NotionWriteAttempt:
    """Per-attempt record the executor collects, regardless of
    success / failure. Mirrors :class:`ClaudeInvocationRecord` from
    MKT-4B at the same observability level."""

    task_id: str
    ok: bool
    page_id: str | None = None
    duration_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    attempted_at: str | None = None


@dataclass(frozen=True)
class NotionPageRequest:
    """Everything a writer needs to make a single create_page call."""

    task_id: str
    database_id: str
    properties: dict[str, Any]
    """Notion page-property dict already shaped by MKT-4E's
    ``to_notion_payload``; the writer passes it through verbatim."""

    record_sink: list | None = None
    """Optional list to receive a :class:`NotionWriteAttempt` for
    each call (success or failure). Same channel as the
    ``ClaudeInvocationContext.record_sink`` from MKT-4B."""


class NotionWriter(ABC):
    """One method: ``create_page``. Implementations:

    - MUST NOT raise except via :class:`NotionWriteError` subclasses.
    - MUST NOT call any Notion API other than the create-page
      endpoint.
    - MUST NOT log the token.
    """

    @abstractmethod
    def create_page(self, request: NotionPageRequest) -> NotionWriteResult: ...


def _truncate(msg: str) -> str:
    msg = (msg or "").strip().replace("\n", " ")
    return msg[:_MAX_ERROR_LEN]


# ---------- shipped writers ----------


class RefusingNotionWriter(NotionWriter):
    """Safe default. Always raises :class:`NoNotionCredentialsError`.

    Wired by the CLI when ``--write --confirm`` is NOT both set, or
    when the env vars are missing. Every call fails fast; the
    executor records "skipped: writer refused" and continues.
    """

    def create_page(self, request: NotionPageRequest) -> NotionWriteResult:
        raise NoNotionCredentialsError(
            "RefusingNotionWriter is wired (dry-run, missing credentials, "
            "or unconfirmed write). No Notion call was made."
        )


@dataclass
class ScriptedNotionWriter(NotionWriter):
    """Returns canned ``page_id``s, optionally raising for specific
    task_ids. Test-only."""

    responses: dict[str, str] = field(default_factory=dict)
    """``task_id`` → ``page_id`` to return."""

    errors_for: dict[str, Exception] = field(default_factory=dict)
    """``task_id`` → exception to raise instead. The class name is
    surfaced in the resulting :class:`NotionWriteError`."""

    calls: list[NotionPageRequest] = field(default_factory=list, init=False, repr=False)

    def create_page(self, request: NotionPageRequest) -> NotionWriteResult:
        self.calls.append(request)
        if request.task_id in self.errors_for:
            exc = self.errors_for[request.task_id]
            error_type = type(exc).__name__
            sanitised = _truncate(str(exc))
            attempt = NotionWriteAttempt(
                task_id=request.task_id,
                ok=False,
                error_type=error_type,
                error_message=sanitised,
            )
            if request.record_sink is not None:
                request.record_sink.append(attempt)
            raise NotionWriteError(f"{error_type}: {sanitised}") from exc

        page_id = self.responses.get(request.task_id) or f"page-for-{request.task_id[:8]}"
        result = NotionWriteResult(page_id=page_id, request_id=f"req-{page_id}")
        if request.record_sink is not None:
            request.record_sink.append(
                NotionWriteAttempt(
                    task_id=request.task_id,
                    ok=True,
                    page_id=page_id,
                )
            )
        return result


class NotionClientWriter(NotionWriter):
    """Production writer backed by the official ``notion-client``
    SDK. The SDK is an OPTIONAL dependency under the ``notion``
    extra; the import is lazy so missing-package environments
    degrade gracefully into a :class:`NoNotionCredentialsError` at
    construction time."""

    def __init__(
        self,
        token: str | None = None,
        *,
        database_id: str | None = None,
        timeout_s: float = 30.0,
        client: Any = None,
    ) -> None:
        import os

        resolved_token = token if token is not None else os.environ.get(_TOKEN_ENV)
        if not resolved_token:
            raise NoNotionCredentialsError(
                f"{_TOKEN_ENV} is not set; NotionClientWriter cannot be "
                "constructed. The CLI falls back to dry-run."
            )

        resolved_db = database_id or os.environ.get(_DATABASE_ID_ENV)
        if not resolved_db:
            raise NoNotionCredentialsError(
                f"{_DATABASE_ID_ENV} is not set; NotionClientWriter requires "
                "an existing tasks database id. The CLI falls back to dry-run."
            )

        resolved_client = client
        if resolved_client is None:
            try:
                from notion_client import Client as _NotionClient
            except ImportError as e:
                raise NoNotionCredentialsError(
                    "The `notion-client` package is not installed. Install "
                    "with `pip install -e .[notion]`. The CLI falls back "
                    "to dry-run."
                ) from e
            resolved_client = _NotionClient(auth=resolved_token, timeout_ms=int(timeout_s * 1000))

        self._database_id = resolved_db
        self._timeout_s = timeout_s
        self._client = resolved_client

    def __repr__(self) -> str:
        return (
            f"NotionClientWriter(token={_REDACTED}, "
            f"database_id={self._database_id[:4]}…, timeout_s={self._timeout_s})"
        )

    @property
    def database_id(self) -> str:
        return self._database_id

    def create_page(self, request: NotionPageRequest) -> NotionWriteResult:
        sink = request.record_sink
        start = time.perf_counter()
        # Defensive: a future caller might pass an empty dict; the
        # SDK would reject it but we want a clean wrapped error.
        if not request.properties:
            duration_ms = (time.perf_counter() - start) * 1000.0
            if sink is not None:
                sink.append(
                    NotionWriteAttempt(
                        task_id=request.task_id,
                        ok=False,
                        duration_ms=duration_ms,
                        error_type="EmptyPropertiesError",
                        error_message="properties dict is empty; refusing to create page.",
                    )
                )
            raise NotionWriteError("properties dict is empty")

        try:
            response = self._client.pages.create(
                parent={"database_id": request.database_id or self._database_id},
                properties=request.properties,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            error_type = type(exc).__name__
            sanitised = _truncate(str(exc))
            if sink is not None:
                sink.append(
                    NotionWriteAttempt(
                        task_id=request.task_id,
                        ok=False,
                        duration_ms=duration_ms,
                        error_type=error_type,
                        error_message=sanitised,
                    )
                )
            raise NotionWriteError(f"{error_type}: {sanitised}") from exc

        duration_ms = (time.perf_counter() - start) * 1000.0
        page_id = self._extract_page_id(response)
        if sink is not None:
            sink.append(
                NotionWriteAttempt(
                    task_id=request.task_id,
                    ok=True,
                    page_id=page_id,
                    duration_ms=duration_ms,
                )
            )
        return NotionWriteResult(page_id=page_id, duration_ms=duration_ms)

    @staticmethod
    def _extract_page_id(response: Any) -> str:
        pid = (
            response.get("id")
            if isinstance(response, dict)
            else getattr(response, "id", None)
        )
        if not isinstance(pid, str) or not pid:
            return "unknown"
        return pid


__all__ = [
    "NoNotionCredentialsError",
    "NotionClientWriter",
    "NotionPageRequest",
    "NotionWriteAttempt",
    "NotionWriteError",
    "NotionWriteResult",
    "NotionWriter",
    "RefusingNotionWriter",
    "ScriptedNotionWriter",
]
