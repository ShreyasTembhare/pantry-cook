from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_graph
from app.api.meals import meal_to_read
from app.db.models import CookSession
from app.db.repositories import CookSessionRepository, ItemRepository, MealRepository
from app.domain.errors import (
    CookFailedError,
    EmptyPantryError,
    SessionBusyError,
    SessionNotAwaitingError,
    StaleProposalError,
)
from app.domain.etag import proposal_etag
from app.graph.state import initial_cook_state
from app.schemas.cook import (
    CookConfirmRequest,
    CookReviseRequest,
    CookSessionRead,
    CookStartRequest,
)
from app.schemas.llm import MealProposal, Violation
from app.schemas.meals import MealRead

router = APIRouter(prefix="/api/cook", tags=["cook"])

_locks_guard = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}


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


def _read_session(row: CookSession, graph: Any) -> CookSessionRead:
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
        meal_id=row.meal_id,
        error=row.last_error if isinstance(row.last_error, dict) else None,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        expires_at=_iso(row.expires_at),
    )


def _apply_outcome(row: CookSession, snapshot: Any) -> None:
    values = _values(snapshot)
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


def _heal_running(row: CookSession, graph: Any) -> None:
    """Recover a session left ``running`` by a crash before the row was updated."""
    if row.status != "running":
        return
    snapshot = _snapshot(graph, row.id)
    if not _values(snapshot) and not tuple(getattr(snapshot, "next", ()) or ()):
        return
    _apply_outcome(row, snapshot)


def _require_awaiting(row: CookSession) -> None:
    if row.status != "awaiting_user":
        raise SessionNotAwaitingError(row.status)


@router.post("/start", status_code=201, response_model=CookSessionRead)
def start_cook(
    body: CookStartRequest,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    if not ItemRepository(db).list():
        raise EmptyPantryError()
    row = CookSessionRepository(db).create(body.sentence)
    db.commit()
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


@router.get("/{thread_id}", response_model=CookSessionRead)
def get_cook(
    thread_id: str,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    row = CookSessionRepository(db).get(thread_id)
    _heal_running(row, graph)
    if db.is_modified(row):
        CookSessionRepository(db).touch(row)
        db.commit()
        db.refresh(row)
    return _read_session(row, graph)


@router.post("/{thread_id}/revise", response_model=CookSessionRead)
def revise_cook(
    thread_id: str,
    body: CookReviseRequest,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    return _resume(db, graph, thread_id, {"decision": "revise", "note": body.note})


@router.post("/{thread_id}/confirm", response_model=MealRead)
def confirm_cook(
    thread_id: str,
    body: CookConfirmRequest,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
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


@router.post("/{thread_id}/abandon", response_model=CookSessionRead)
def abandon_cook(
    thread_id: str,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
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
