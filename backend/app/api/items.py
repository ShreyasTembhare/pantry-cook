from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_sentence_llm
from app.api.error_handlers import problem_responses
from app.schemas.items import ItemCreate, ItemMerge, ItemRead, ItemUpdate
from app.schemas.quick_add import PantrySentenceCommit, PantrySentencePreview, SentenceRequest
from app.services.pantry import PantryService

router = APIRouter(prefix="/api/items", tags=["items"])


@router.post("", status_code=201, response_model=ItemRead, responses=problem_responses(409, 422))
def create_item(
    body: ItemCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    return PantryService(db).create(body)


@router.get("", response_model=list[ItemRead], responses=problem_responses(422))
def list_items(
    sort: Literal["expires_on", "name", "created_at"] = "expires_on",
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ItemRead]:
    return PantryService(db).list(sort)


@router.post(
    "/sentence/preview",
    response_model=PantrySentencePreview,
    responses=problem_responses(422, 429, 502, 504),
)
def preview_sentence(
    body: SentenceRequest,
    db: Session = Depends(get_db),  # noqa: B008
    llm: Any = Depends(get_sentence_llm),  # noqa: B008
) -> PantrySentencePreview:
    return PantryService(db, llm).preview_sentence(body)


@router.post("/sentence", response_model=list[ItemRead], responses=problem_responses(409, 422))
def save_sentence(
    body: PantrySentenceCommit,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ItemRead]:
    return PantryService(db).save_sentence(body)


@router.get("/{item_id}", response_model=ItemRead, responses=problem_responses(404))
def get_item(
    item_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    return PantryService(db).get(item_id)


@router.patch("/{item_id}", response_model=ItemRead, responses=problem_responses(404, 409, 422))
def update_item(
    item_id: str,
    body: ItemUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    return PantryService(db).update(item_id, body)


@router.post(
    "/{item_id}/merge", response_model=ItemRead, responses=problem_responses(404, 409, 422)
)
def merge_item(
    item_id: str,
    body: ItemMerge,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    return PantryService(db).merge(item_id, body)


@router.delete("/{item_id}", status_code=204, responses=problem_responses(404))
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    PantryService(db).delete(item_id)
