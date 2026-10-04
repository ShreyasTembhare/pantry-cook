"""Home conversation. Writes go through the pantry, cook, and meal services."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories import ChatRepository
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
from app.schemas.chat import ChatMessageRead, ChatThreadRead, ChatTurnRead


class ChatService:
    def __init__(self, db: Session, graph: Any | None = None, llm: Any | None = None) -> None:
        self.db = db
        self.graph = graph
        self.llm = llm

    def thread(self) -> ChatThreadRead:
        thread = home_thread(self.db)
        self.db.commit()
        self.db.refresh(thread)
        return ChatThreadRead(
            id=thread.id,
            active_cook_session_id=thread.active_cook_session_id,
            messages=[_read_message(message) for message in thread_messages(self.db, thread)],
        )

    def turn(self, text: str) -> ChatTurnRead:
        return run_turn(self.db, self.graph, self.llm, text)

    def confirm(self, pending_id: str, acknowledge_expired: bool = False) -> ChatMessageRead:
        thread, pending = self._open_pending(pending_id)
        reply, cards = confirm_pending(
            self.db,
            self.graph,
            thread,
            pending,
            acknowledge_expired=acknowledge_expired,
        )
        message = _append(self.db, thread, "assistant", reply, cards)
        self.db.commit()
        self.db.refresh(message)
        return _read_message(message)

    def cancel(self, pending_id: str) -> ChatMessageRead:
        thread, pending = self._open_pending(pending_id)
        reply, cards = cancel_pending(self.db, pending)
        message = _append(self.db, thread, "assistant", reply, cards)
        self.db.commit()
        self.db.refresh(message)
        return _read_message(message)

    def _open_pending(self, pending_id: str) -> tuple[Any, Any]:
        thread = home_thread(self.db)
        pending = ChatRepository(self.db).get_pending(pending_id)
        if pending is None or pending.thread_id != thread.id:
            raise DomainError("pending_not_found", 404, "That confirmation is gone.")
        if pending.status != "open":
            raise DomainError("pending_closed", 409, "That confirmation is no longer open.")
        return thread, pending
