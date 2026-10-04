from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_graph
from app.api.error_handlers import problem_responses
from app.schemas.cook import (
    CookConfirmRequest,
    CookReviseRequest,
    CookSessionRead,
    CookSessionSummary,
    CookStartRequest,
)
from app.schemas.meals import MealRead
from app.services.cook import CookService

router = APIRouter(prefix="/api/cook", tags=["cook"])


@router.post(
    "/start",
    status_code=201,
    response_model=CookSessionRead,
    responses=problem_responses(409, 422, 429, 502, 504),
)
def start_cook(
    body: CookStartRequest,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    return CookService(db, graph).start(body)


@router.get("", response_model=list[CookSessionSummary], responses=problem_responses(422))
def list_cook_sessions(
    status: Literal[
        "running", "awaiting_user", "committed", "abandoned", "failed"
    ] = "awaiting_user",
    db: Session = Depends(get_db),  # noqa: B008
) -> list[CookSessionSummary]:
    return CookService(db, graph=None).list(status)


@router.get(
    "/{thread_id}",
    response_model=CookSessionRead,
    responses=problem_responses(404, 409, 422, 429, 502, 504),
)
def get_cook(
    thread_id: str,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    return CookService(db, graph).get(thread_id)


@router.post(
    "/{thread_id}/revise",
    response_model=CookSessionRead,
    responses=problem_responses(404, 409, 422, 429, 502, 504),
)
def revise_cook(
    thread_id: str,
    body: CookReviseRequest,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    return CookService(db, graph).revise(thread_id, body)


@router.post(
    "/{thread_id}/confirm",
    response_model=MealRead,
    responses=problem_responses(404, 409, 422, 429, 502, 504),
)
def confirm_cook(
    thread_id: str,
    body: CookConfirmRequest,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> MealRead:
    return CookService(db, graph).confirm(thread_id, body)


@router.post(
    "/{thread_id}/abandon",
    response_model=CookSessionRead,
    responses=problem_responses(404, 409),
)
def abandon_cook(
    thread_id: str,
    db: Session = Depends(get_db),  # noqa: B008
    graph: Any = Depends(get_graph),  # noqa: B008
) -> CookSessionRead:
    return CookService(db, graph).abandon(thread_id)
