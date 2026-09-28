"""Startup reconcile and the hourly sweep of abandoned cook sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.db.models import CookSession
from app.db.repositories import CookSessionRepository

STUCK_AFTER = timedelta(minutes=10)
CHECKPOINT_RETENTION = timedelta(days=7)
SWEEP_INTERVAL_SECONDS = 3600

_log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def snapshot_values(snapshot: Any) -> dict[str, Any]:
    values = getattr(snapshot, "values", None) or {}
    return values if isinstance(values, dict) else {}


def apply_checkpoint(row: CookSession, snapshot: Any) -> None:
    """Copy a finished graph snapshot onto the session row."""
    values = snapshot_values(snapshot)
    pending = tuple(getattr(snapshot, "next", ()) or ())
    row.attempt_count = len(values.get("attempts") or [])
    if pending:
        row.status = "awaiting_user"
        row.last_error = None
        return
    if values.get("decision") == "abandon":
        row.status = "abandoned"
        row.last_error = None
        return
    result = values.get("result")
    if isinstance(result, dict) and result.get("meal_id"):
        row.status = "committed"
        row.meal_id = str(result["meal_id"])
        row.last_error = None
        return
    error = values.get("error")
    row.status = "failed"
    row.last_error = (
        error
        if isinstance(error, dict)
        else {
            "code": "cook_failed",
            "detail": "The cook session ended without a result.",
        }
    )


def _waiting_on_user(snapshot: Any) -> bool:
    pending = tuple(getattr(snapshot, "next", ()) or ())
    if "await_user" in pending:
        return True
    tasks = getattr(snapshot, "tasks", ()) or ()
    return any(getattr(task, "interrupts", None) for task in tasks)


def _fail(row: CookSession, code: str, *, cause: str | None = None) -> None:
    error: dict[str, object] = {
        "code": code,
        "detail": "This session was interrupted.",
    }
    if cause:
        error["cause"] = cause
    row.status = "failed"
    row.last_error = error


def heal_if_running(row: CookSession, graph: Any) -> None:
    """Recover a session left ``running`` after the graph had already paused.

    An unreadable checkpoint becomes ``failed`` with ``checkpoint_unreadable``
    instead of a 500 on the next read.
    """
    if row.status != "running":
        return
    try:
        snapshot = graph.get_state({"configurable": {"thread_id": row.id}})
    except Exception as exc:
        _fail(row, "checkpoint_unreadable", cause=type(exc).__name__)
        return
    if not snapshot_values(snapshot) and not tuple(getattr(snapshot, "next", ()) or ()):
        return
    apply_checkpoint(row, snapshot)


def reconcile_running_sessions(
    db: Session,
    graph: Any,
    *,
    now: datetime | None = None,
    stuck_after: timedelta = STUCK_AFTER,
) -> int:
    """Fail cooks that died mid-call, and resume ones waiting at the interrupt.

    A ``running`` row older than ``stuck_after`` with no user interrupt is
    ``interrupted_by_restart``. A checkpoint the library can no longer read is
    ``checkpoint_unreadable``.
    """
    moment = now or _now()
    changed = 0
    for row in CookSessionRepository(db).list("running"):
        try:
            snapshot = graph.get_state({"configurable": {"thread_id": row.id}})
        except Exception as exc:
            _fail(row, "checkpoint_unreadable", cause=type(exc).__name__)
            row.updated_at = moment
            changed += 1
            continue
        if _waiting_on_user(snapshot):
            apply_checkpoint(row, snapshot)
            row.updated_at = moment
            changed += 1
            continue
        if moment - _as_naive(row.updated_at) >= stuck_after:
            _fail(row, "interrupted_by_restart")
            row.updated_at = moment
            changed += 1
    return changed


def sweep_expired_sessions(
    db: Session,
    checkpointer: Any | None,
    *,
    now: datetime | None = None,
    retention: timedelta = CHECKPOINT_RETENTION,
) -> tuple[int, int]:
    """Abandon proposals past ``expires_at`` and drop old checkpoints.

    Returns ``(abandoned, checkpoints_deleted)``.
    """
    moment = now or _now()
    abandoned = 0
    for row in CookSessionRepository(db).list("awaiting_user"):
        if _as_naive(row.expires_at) <= moment:
            row.status = "abandoned"
            row.last_error = None
            row.updated_at = moment
            abandoned += 1

    deleted = 0
    if checkpointer is None or not hasattr(checkpointer, "delete_thread"):
        return abandoned, deleted
    cutoff = moment - retention
    for row in CookSessionRepository(db).list_finished_before(cutoff):
        try:
            checkpointer.delete_thread(row.id)
        except Exception:
            _log.warning("checkpoint_delete_failed", session_id=row.id)
            continue
        deleted += 1
    return abandoned, deleted


def run_session_maintenance(db: Session, graph: Any, *, now: datetime | None = None) -> None:
    """Reconcile, then sweep. Caller commits."""
    reconciled = reconcile_running_sessions(db, graph, now=now)
    checkpointer = getattr(graph, "checkpointer", None)
    abandoned, deleted = sweep_expired_sessions(db, checkpointer, now=now)
    _log.info(
        "session_maintenance",
        reconciled=reconciled,
        abandoned=abandoned,
        checkpoints_deleted=deleted,
    )
