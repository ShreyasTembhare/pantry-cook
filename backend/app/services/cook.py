"""Cook session writes shared by the cook API, the cook stream, and chat."""

from __future__ import annotations

import threading
from typing import Any, Literal

from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.db.models import CookSession, Item
from app.db.repositories import CookSessionRepository, ItemRepository, MealRepository
from app.domain.errors import (
    CookFailedError,
    EmptyPantryError,
    ExpiredUnacknowledgedError,
    SessionBusyError,
    SessionNotAwaitingError,
    StaleProposalError,
)
from app.domain.etag import proposal_etag
from app.domain.expiry import is_expired
from app.domain.sessions import apply_checkpoint, heal_if_running
from app.graph.state import initial_cook_state
from app.schemas.cook import (
    CookConfirmRequest,
    CookReviseRequest,
    CookSessionRead,
    CookSessionSummary,
    CookStartRequest,
    read_proposal_attempts,
)
from app.schemas.llm import MealProposal, Violation
from app.schemas.meals import MealRead
from app.services.reading import meal_to_read

_locks_guard = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}
# Resume payloads armed by a deferred revise. The stream endpoint consumes them.
_pending_resume: dict[str, dict[str, Any]] = {}


def _session_lock(session_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _session_locks[session_id] = lock
        return lock


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _invoke(graph: Any, payload: Any, thread_id: str) -> None:
    try:
        graph.invoke(payload, _config(thread_id), durability="sync")
    except GraphInterrupt:
        return


def _snapshot(graph: Any, thread_id: str) -> Any:
    return graph.get_state(_config(thread_id))


def _values(snapshot: Any) -> dict[str, Any]:
    values = getattr(snapshot, "values", None) or {}
    return values if isinstance(values, dict) else {}


def _iso(value: Any) -> str:
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _read_session(row: CookSession, graph: Any, db: Session | None = None) -> CookSessionRead:
    del db
    snapshot = _snapshot(graph, row.id)
    values = _values(snapshot)
    proposal_raw = values.get("proposal")
    proposal = MealProposal.model_validate(proposal_raw) if proposal_raw else None
    violations = [Violation.model_validate(item) for item in values.get("violations") or []]
    etag = None
    if proposal_raw:
        etag = proposal_etag(proposal_raw, list(values.get("pantry_snapshot") or []))
    return CookSessionRead(
        id=row.id,
        status=row.status,  # type: ignore[arg-type]
        sentence=row.sentence,
        attempt_count=row.attempt_count,
        proposal=proposal,
        proposal_etag=etag,
        violations=violations,
        attempts=read_proposal_attempts(values),
        meal_id=row.meal_id,
        error=row.last_error if isinstance(row.last_error, dict) else None,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        expires_at=_iso(row.expires_at),
    )


def _apply_outcome(row: CookSession, snapshot: Any) -> None:
    apply_checkpoint(row, snapshot)


def _heal_running(row: CookSession, graph: Any) -> None:
    """Recover a session left ``running`` by a crash before the row was updated."""
    heal_if_running(row, graph)


def _expired_uses(db: Session, proposal: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in proposal.get("lines") or []:
        if not isinstance(line, dict) or line.get("kind") != "use":
            continue
        item_id = line.get("item_id")
        if not isinstance(item_id, str) or item_id in seen:
            continue
        item = db.get(Item, item_id)
        if item is None or not is_expired(item.expires_on):
            continue
        seen.add(item_id)
        found.append(
            {
                "item_id": item.id,
                "name": item.name,
                "expires_on": item.expires_on.isoformat() if item.expires_on else "",
            }
        )
    return found


def _require_awaiting(row: CookSession) -> None:
    if row.status != "awaiting_user":
        raise SessionNotAwaitingError(row.status)


def start_cook(
    body: CookStartRequest,
    db: Session,
    graph: Any,
) -> CookSessionRead:
    if not ItemRepository(db).list():
        raise EmptyPantryError()
    row = CookSessionRepository(db).create(body.sentence)
    db.commit()
    if body.defer:
        db.refresh(row)
        return _read_session(row, graph)
    thread_id = row.id
    lock = _session_lock(thread_id)
    if not lock.acquire(blocking=False):
        raise SessionBusyError()
    try:
        _invoke(graph, initial_cook_state(thread_id, body.sentence), thread_id)
        db.refresh(row)
        _apply_outcome(row, _snapshot(graph, thread_id))
        CookSessionRepository(db).touch(row)
        db.commit()
        db.refresh(row)
        if row.status == "failed" and isinstance(row.last_error, dict):
            raise CookFailedError(row.last_error)
        return _read_session(row, graph)
    finally:
        lock.release()


def list_cook_sessions(
    db: Session,
    status: Literal[
        "running", "awaiting_user", "committed", "abandoned", "failed"
    ] = "awaiting_user",
) -> list[CookSessionSummary]:
    rows = CookSessionRepository(db).list(status)
    return [
        CookSessionSummary(
            id=row.id,
            status=row.status,  # type: ignore[arg-type]
            sentence=row.sentence,
            attempt_count=row.attempt_count,
            updated_at=_iso(row.updated_at),
        )
        for row in rows
    ]


def get_cook(thread_id: str, db: Session, graph: Any) -> CookSessionRead:
    row = CookSessionRepository(db).get(thread_id)
    _heal_running(row, graph)
    if db.is_modified(row):
        CookSessionRepository(db).touch(row)
        db.commit()
        db.refresh(row)
    return _read_session(row, graph)


def revise_cook(
    thread_id: str,
    body: CookReviseRequest,
    db: Session,
    graph: Any,
) -> CookSessionRead:
    payload = {"decision": "revise", "note": body.note}
    if body.defer:
        return _arm_resume(db, graph, thread_id, payload)
    return _resume(db, graph, thread_id, payload)


def confirm_cook(
    thread_id: str,
    body: CookConfirmRequest,
    db: Session,
    graph: Any,
) -> MealRead:
    lock = _session_lock(thread_id)
    if not lock.acquire(blocking=False):
        raise SessionBusyError()
    try:
        repo = CookSessionRepository(db)
        row = repo.get(thread_id)
        _heal_running(row, graph)
        _require_awaiting(row)
        values = _values(_snapshot(graph, thread_id))
        proposal = values.get("proposal")
        if not isinstance(proposal, dict):
            raise SessionNotAwaitingError(row.status)
        expected = proposal_etag(proposal, list(values.get("pantry_snapshot") or []))
        if body.proposal_etag != expected:
            raise StaleProposalError(reason="proposal_etag_mismatch")
        expired = _expired_uses(db, proposal)
        if expired and not body.acknowledge_expired:
            raise ExpiredUnacknowledgedError(expired)

        row.status = "running"
        repo.touch(row)
        db.commit()

        _invoke(graph, Command(resume={"decision": "confirm"}), thread_id)
        db.refresh(row)
        snapshot = _snapshot(graph, thread_id)
        _apply_outcome(row, snapshot)
        repo.touch(row)
        db.commit()
        db.refresh(row)

        error = _values(snapshot).get("error")
        if isinstance(error, dict) and error.get("code") == "stale_proposal":
            changed = error.get("changed_item_ids")
            raise StaleProposalError(list(changed) if isinstance(changed, list) else [])
        if row.status == "failed" and isinstance(row.last_error, dict):
            raise CookFailedError(row.last_error)
        if not row.meal_id:
            raise CookFailedError(
                {"code": "cook_failed", "detail": "Confirm did not produce a meal."}
            )
        return meal_to_read(MealRepository(db).get(row.meal_id))
    finally:
        lock.release()


def abandon_cook(thread_id: str, db: Session, graph: Any) -> CookSessionRead:
    lock = _session_lock(thread_id)
    if not lock.acquire(blocking=False):
        raise SessionBusyError()
    try:
        repo = CookSessionRepository(db)
        row = repo.get(thread_id)
        _heal_running(row, graph)
        if row.status == "abandoned":
            db.commit()
            return _read_session(row, graph)
        _require_awaiting(row)
        row.status = "running"
        repo.touch(row)
        db.commit()
        _invoke(graph, Command(resume={"decision": "abandon"}), thread_id)
        db.refresh(row)
        _apply_outcome(row, _snapshot(graph, thread_id))
        repo.touch(row)
        db.commit()
        db.refresh(row)
        return _read_session(row, graph)
    finally:
        lock.release()


def _arm_resume(
    db: Session, graph: Any, thread_id: str, payload: dict[str, Any]
) -> CookSessionRead:
    """Mark the session running and let the stream endpoint resume the graph."""
    lock = _session_lock(thread_id)
    if not lock.acquire(blocking=False):
        raise SessionBusyError()
    try:
        repo = CookSessionRepository(db)
        row = repo.get(thread_id)
        _heal_running(row, graph)
        _require_awaiting(row)
        _pending_resume[thread_id] = payload
        row.status = "running"
        repo.touch(row)
        db.commit()
        db.refresh(row)
        return _read_session(row, graph)
    finally:
        lock.release()


def _resume(db: Session, graph: Any, thread_id: str, payload: dict[str, Any]) -> CookSessionRead:
    lock = _session_lock(thread_id)
    if not lock.acquire(blocking=False):
        raise SessionBusyError()
    try:
        repo = CookSessionRepository(db)
        row = repo.get(thread_id)
        _heal_running(row, graph)
        _require_awaiting(row)
        row.status = "running"
        repo.touch(row)
        db.commit()
        _invoke(graph, Command(resume=payload), thread_id)
        db.refresh(row)
        _apply_outcome(row, _snapshot(graph, thread_id))
        repo.touch(row)
        db.commit()
        db.refresh(row)
        if row.status == "failed" and isinstance(row.last_error, dict):
            raise CookFailedError(row.last_error)
        return _read_session(row, graph)
    finally:
        lock.release()


class CookService:
    """One cook graph and one database session."""

    def __init__(self, db: Session, graph: Any) -> None:
        self.db = db
        self.graph = graph

    def start(self, body: CookStartRequest) -> CookSessionRead:
        return start_cook(body, self.db, self.graph)

    def list(
        self,
        status: Literal[
            "running", "awaiting_user", "committed", "abandoned", "failed"
        ] = "awaiting_user",
    ) -> list[CookSessionSummary]:
        return list_cook_sessions(self.db, status)

    def get(self, thread_id: str) -> CookSessionRead:
        return get_cook(thread_id, self.db, self.graph)

    def revise(self, thread_id: str, body: CookReviseRequest) -> CookSessionRead:
        return revise_cook(thread_id, body, self.db, self.graph)

    def confirm(self, thread_id: str, body: CookConfirmRequest) -> MealRead:
        return confirm_cook(thread_id, body, self.db, self.graph)

    def abandon(self, thread_id: str) -> CookSessionRead:
        return abandon_cook(thread_id, self.db, self.graph)
