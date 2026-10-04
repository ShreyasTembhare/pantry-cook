"""Home conversation: one thread, structured plans, explicit confirms."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_chat_model, get_db, get_graph
from app.db.models import ChatPending
from app.domain.chat import (
    _append,
    _read_message,
    cancel_pending,
    confirm_pending,
    home_thread,
    run_turn,
    thread_messages,
)
from app.domain.errors import DomainError
from app.schemas.chat import (
    ChatMessageIn,
    ChatMessageRead,
    ChatThreadRead,
    ChatTurnRead,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _thread_read(db: Session) -> ChatThreadRead:
    thread = home_thread(db)
    db.commit()
    db.refresh(thread)
    return ChatThreadRead(
        id=thread.id,
        active_cook_session_id=thread.active_cook_session_id,
        messages=[_read_message(message) for message in thread_messages(db, thread)],
    )


def _pending_or_404(db: Session, pending_id: str) -> tuple[Any, ChatPending]:
    thread = home_thread(db)
    pending = db.get(ChatPending, pending_id)
    if pending is None or pending.thread_id != thread.id:
        raise DomainError("pending_not_found", 404, "That confirmation is gone.")
    if pending.status != "open":
        raise DomainError("pending_closed", 409, "That confirmation is no longer open.")
    return thread, pending


@router.get("", response_model=ChatThreadRead)
def get_chat(db: Session = Depends(get_db)) -> ChatThreadRead:  # noqa: B008
    return _thread_read(db)


@router.post("/messages", response_model=ChatTurnRead)
def post_message(
    body: ChatMessageIn,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
    llm: Any = Depends(get_chat_model),  # noqa: B008
) -> ChatTurnRead:
    return run_turn(db, graph, llm, body.text)


@router.get("/stream")
def stream_message(
    text: str,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
    llm: Any = Depends(get_chat_model),  # noqa: B008
) -> StreamingResponse:
    """Run one turn and emit thinking, the turn, then done.

    EventSource cannot POST, so the composer text rides on the query string.
    """

    def events() -> Iterator[str]:
        yield _sse("status", {"state": "thinking"})
        turn = run_turn(db, graph, llm, text)
        yield _sse("turn", turn.model_dump(mode="json"))
        yield _sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/pending/{pending_id}/confirm", response_model=ChatMessageRead)
def confirm_chat_pending(
    pending_id: str,
    acknowledge_expired: bool = False,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> ChatMessageRead:
    thread, pending = _pending_or_404(db, pending_id)
    reply, cards = confirm_pending(
        db,
        graph,
        thread,
        pending,
        acknowledge_expired=acknowledge_expired,
    )
    message = _append(db, thread, "assistant", reply, cards)
    db.commit()
    db.refresh(message)
    return _read_message(message)


@router.post("/pending/{pending_id}/cancel", response_model=ChatMessageRead)
def cancel_chat_pending(
    pending_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> ChatMessageRead:
    thread, pending = _pending_or_404(db, pending_id)
    reply, cards = cancel_pending(db, pending)
    message = _append(db, thread, "assistant", reply, cards)
    db.commit()
    db.refresh(message)
    return _read_message(message)


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
