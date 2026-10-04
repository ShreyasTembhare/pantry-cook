from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal

_graph: Any = None
_checkpointer: Any = None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_graph() -> Any:
    """Open the checkpointer and compile the cook graph once per process."""
    global _graph, _checkpointer
    if _graph is not None:
        return _graph

    from app.config import settings
    from app.graph.builder import build_graph
    from app.graph.checkpointer import open_postgres_saver
    from app.graph.llm import get_llm

    _checkpointer = open_postgres_saver(settings.database_url)
    _graph = build_graph(_checkpointer, get_llm(settings), SessionLocal)
    return _graph


def close_graph() -> None:
    global _graph, _checkpointer
    conn = getattr(_checkpointer, "conn", None)
    if conn is not None:
        conn.close()
    _checkpointer = None
    _graph = None


def get_graph() -> Any:
    if _graph is None:
        return init_graph()
    return _graph


def get_sentence_llm() -> Any:
    """Offline chef unless a provider key is configured. Tests can override this."""
    from app.graph.llm import get_llm

    return get_llm()


def get_chat_model() -> Any:
    """Same chef as cook and quick-add. Tests override this with the fake model."""
    return get_sentence_llm()
