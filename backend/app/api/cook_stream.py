"""Server-sent events for a cook run.

The graph runs in a task that outlives any one HTTP connection, so a dropped
browser can reconnect and catch up. Events come from ``graph.astream`` in
``updates`` and ``messages`` mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db, get_graph
from app.api.error_handlers import problem_responses
from app.db.repositories import CookSessionRepository
from app.graph.state import initial_cook_state
from app.schemas.cook import CookSessionRead
from app.services.cook import (
    _apply_outcome,
    _config,
    _pending_resume,
    _read_session,
    _session_lock,
    _snapshot,
    _values,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cook", tags=["cook"])

_runs_guard = threading.Lock()
_runs: dict[str, _CookRun] = {}

_REPLAY_NODES = ("load_pantry", "parse_sentence", "propose_meal", "validate_proposal")


class _CookRun:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.finished = False
        self.condition = asyncio.Condition()
        self.task: asyncio.Task[None] | None = None

    async def add(self, event: str, data: Any) -> None:
        async with self.condition:
            self.events.append((event, data))
            self.condition.notify_all()

    async def finish(self) -> None:
        async with self.condition:
            self.finished = True
            self.condition.notify_all()


def _format(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _unpack(chunk: Any) -> tuple[str, Any]:
    if (
        isinstance(chunk, tuple)
        and len(chunk) == 2
        and chunk[0] in {"updates", "messages", "values", "custom"}
    ):
        return str(chunk[0]), chunk[1]
    return "updates", chunk


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _events_from_chunk(chunk: Any) -> list[tuple[str, Any]]:
    mode, data = _unpack(chunk)
    if mode == "messages":
        message: Any
        meta: dict[str, Any]
        if isinstance(data, tuple) and len(data) == 2:
            message, raw_meta = data
            meta = raw_meta if isinstance(raw_meta, dict) else {}
        else:
            message, meta = data, {}
        if meta.get("langgraph_node") != "propose_meal":
            return []
        text = _message_text(message)
        if not text:
            return []
        return [("proposal_token", {"text": text})]

    if mode != "updates" or not isinstance(data, dict):
        return []

    events: list[tuple[str, Any]] = []
    for node, update in data.items():
        if not isinstance(node, str) or node.startswith("__"):
            continue
        events.append(("node_started", {"node": node}))
        if not isinstance(update, dict):
            continue
        if node == "parse_sentence" and update.get("constraints"):
            events.append(("constraints", update["constraints"]))
        if node == "propose_meal" and update.get("proposal"):
            events.append(("proposal", update["proposal"]))
        if node == "validate_proposal":
            for violation in update.get("violations") or []:
                events.append(("violation", violation))
        error = update.get("error")
        if isinstance(error, dict) and error.get("code"):
            events.append(("error", error))
    return events


def _replay_events(session: CookSessionRead) -> list[tuple[str, Any]]:
    dumped = session.model_dump(mode="json")
    events: list[tuple[str, Any]] = [("node_started", {"node": node}) for node in _REPLAY_NODES]
    proposal = dumped.get("proposal")
    if proposal:
        events.append(("proposal", proposal))
    for violation in dumped.get("violations") or []:
        events.append(("violation", violation))
    if session.status == "awaiting_user":
        events.append(
            (
                "awaiting_user",
                {"attempt": session.attempt_count, "proposal_etag": session.proposal_etag},
            )
        )
    if session.status == "failed" and isinstance(session.error, dict):
        events.append(("error", session.error))
    events.append(("done", {"status": session.status, "session": dumped}))
    return events


async def _subscribe(run: _CookRun) -> AsyncIterator[str]:
    index = 0
    while True:
        async with run.condition:
            while index >= len(run.events) and not run.finished:
                await run.condition.wait()
            batch = list(run.events[index:])
            index = len(run.events)
            finished = run.finished
        for event, data in batch:
            yield _format(event, data)
        if finished:
            return


async def _drive(
    factory: sessionmaker[Session],
    graph: Any,
    thread_id: str,
    payload: Any,
    run: _CookRun,
) -> None:
    lock = _session_lock(thread_id)
    if not lock.acquire(blocking=False):
        await run.add("busy", {"status": "running"})
        await run.finish()
        return
    try:
        try:
            async for chunk in graph.astream(
                payload,
                _config(thread_id),
                stream_mode=["updates", "messages"],
                durability="sync",
            ):
                for event, data in _events_from_chunk(chunk):
                    await run.add(event, data)
        except GraphInterrupt:
            pass
        session = _persist(factory, graph, thread_id)
        dumped = session.model_dump(mode="json")
        if session.status == "awaiting_user":
            await run.add(
                "awaiting_user",
                {"attempt": session.attempt_count, "proposal_etag": session.proposal_etag},
            )
        elif session.status == "failed" and isinstance(session.error, dict):
            await run.add("error", session.error)
        await run.add("done", {"status": session.status, "session": dumped})
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("cook stream failed for %s", thread_id)
        detail = "The cook didn't come back with a meal."
        _mark_failed(factory, thread_id, detail)
        await run.add("error", {"code": "cook_failed", "detail": detail})
        await run.add("done", {"status": "failed"})
    finally:
        lock.release()
        await run.finish()


def _persist(factory: sessionmaker[Session], graph: Any, thread_id: str) -> CookSessionRead:
    db = factory()
    try:
        row = CookSessionRepository(db).get(thread_id)
        _apply_outcome(row, _snapshot(graph, thread_id))
        CookSessionRepository(db).touch(row)
        db.commit()
        db.refresh(row)
        return _read_session(row, graph, db)
    finally:
        db.close()


def _mark_failed(factory: sessionmaker[Session], thread_id: str, detail: str) -> None:
    db = factory()
    try:
        row = CookSessionRepository(db).get(thread_id)
        row.status = "failed"
        row.last_error = {"code": "cook_failed", "detail": detail}
        CookSessionRepository(db).touch(row)
        db.commit()
    except Exception:
        logger.exception("could not record cook stream failure for %s", thread_id)
    finally:
        db.close()


def _active_run(thread_id: str) -> _CookRun | None:
    with _runs_guard:
        existing = _runs.get(thread_id)
        if existing and not existing.finished:
            return existing
    return None


async def iter_cook_sse(db: Session, graph: Any, thread_id: str) -> AsyncIterator[str]:
    active = _active_run(thread_id)
    if active is not None:
        async for piece in _subscribe(active):
            yield piece
        return

    repo = CookSessionRepository(db)
    row = repo.get(thread_id)
    snapshot = _snapshot(graph, thread_id)
    interrupted = bool(tuple(getattr(snapshot, "interrupts", ()) or ()))
    nxt = tuple(getattr(snapshot, "next", ()) or ())
    has_checkpoint = bool(_values(snapshot)) or bool(nxt)
    pending = thread_id in _pending_resume

    if row.status != "running":
        for event, data in _replay_events(_read_session(row, graph, db)):
            yield _format(event, data)
        return

    if (interrupted and not pending) or (has_checkpoint and not nxt and not pending):
        _apply_outcome(row, snapshot)
        repo.touch(row)
        db.commit()
        db.refresh(row)
        for event, data in _replay_events(_read_session(row, graph, db)):
            yield _format(event, data)
        return

    with _runs_guard:
        existing = _runs.get(thread_id)
        if existing and not existing.finished:
            run = existing
        else:
            resume = _pending_resume.pop(thread_id, None)
            if resume is not None:
                payload: Any = Command(resume=resume)
            elif has_checkpoint:
                payload = None
            else:
                payload = initial_cook_state(thread_id, row.sentence)
            run = _CookRun()
            _runs[thread_id] = run
            factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
            run.task = asyncio.create_task(_drive(factory, graph, thread_id, payload, run))

    async for piece in _subscribe(run):
        yield piece


@router.get("/{thread_id}/stream", responses=problem_responses(404))
async def stream_cook(
    thread_id: str,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> StreamingResponse:
    CookSessionRepository(db).get(thread_id)
    return StreamingResponse(
        iter_cook_sse(db, graph, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
