"""Home conversation: one thread, structured plans, explicit confirms."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_chat_model, get_db, get_graph
from app.schemas.chat import ChatMessageIn, ChatMessageRead, ChatThreadRead, ChatTurnRead
from app.services.chat import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("", response_model=ChatThreadRead)
def get_chat(db: Session = Depends(get_db)) -> ChatThreadRead:  # noqa: B008
    return ChatService(db).thread()


@router.post("/messages", response_model=ChatTurnRead)
def post_message(
    body: ChatMessageIn,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
    llm: Any = Depends(get_chat_model),  # noqa: B008
) -> ChatTurnRead:
    return ChatService(db, graph, llm).turn(body.text)


@router.post("/pending/{pending_id}/confirm", response_model=ChatMessageRead)
def confirm_chat_pending(
    pending_id: str,
    acknowledge_expired: bool = False,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> ChatMessageRead:
    return ChatService(db, graph).confirm(pending_id, acknowledge_expired)


@router.post("/pending/{pending_id}/cancel", response_model=ChatMessageRead)
def cancel_chat_pending(
    pending_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> ChatMessageRead:
    return ChatService(db).cancel(pending_id)
