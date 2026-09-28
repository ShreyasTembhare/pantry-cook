from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, Any]:  # noqa: B008
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    from app.config import settings

    return {
        "status": "healthy" if db_ok else "degraded",
        "db": "ok" if db_ok else "unreachable",
        "llm": settings.llm_provider,
    }
