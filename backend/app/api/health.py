from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_graph
from app.db.repositories import CookSessionRepository

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check(
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> dict[str, Any]:
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    checkpoint = "unreachable"
    try:
        graph.get_state({"configurable": {"thread_id": "__health__"}})
        checkpoint = "ok"
    except Exception:
        checkpoint = "unreachable"

    from app.graph.llm import llm_mode

    pending = CookSessionRepository(db).count_status("awaiting_user") if db_ok else 0
    healthy = db_ok and checkpoint == "ok"
    return {
        "status": "healthy" if healthy else "degraded",
        "db": "ok" if db_ok else "unreachable",
        "checkpointer": checkpoint,
        "llm": llm_mode(),
        "pending_sessions": pending,
    }
