from __future__ import annotations

import sqlite3
from collections.abc import Generator
from typing import Any

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal

_graph: Any = None
_checkpoint_conn: sqlite3.Connection | None = None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_graph() -> Any:
    """Open the checkpointer and compile the cook graph once per process."""
    global _graph, _checkpoint_conn
    if _graph is not None:
        return _graph

    from langgraph.checkpoint.sqlite import SqliteSaver

    from app.config import settings
    from app.graph.builder import build_graph
    from app.graph.llm import get_llm

    settings.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    _checkpoint_conn = sqlite3.connect(
        str(settings.checkpoint_db_path.resolve()),
        check_same_thread=False,
        timeout=30,
    )
    saver = SqliteSaver(_checkpoint_conn)
    saver.setup()
    _graph = build_graph(saver, get_llm(settings), SessionLocal)
    return _graph


def close_graph() -> None:
    global _graph, _checkpoint_conn
    if _checkpoint_conn is not None:
        _checkpoint_conn.close()
    _checkpoint_conn = None
    _graph = None


def get_graph() -> Any:
    if _graph is None:
        return init_graph()
    return _graph
