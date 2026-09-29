from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_sentence_llm
from app.db.models import Item
from app.db.repositories import ItemRepository
from app.domain.quick_add import (
    commit_parsed_items,
    normalise_draft,
    parse_pantry_sentence,
    preview_lines,
)
from app.domain.units import Dimension, Quantity, Unit
from app.schemas.items import ItemCreate, ItemMerge, ItemRead, ItemUpdate
from app.schemas.quick_add import (
    DraftPantrySentence,
    PantrySentenceCommit,
    PantrySentencePreview,
    SentenceRequest,
)

router = APIRouter(prefix="/api/items", tags=["items"])


def _item_to_read(item: Item) -> ItemRead:
    display_qty = Quantity.from_base(
        item.quantity_base,
        Dimension(item.dimension),
        Unit(item.display_unit),
    )
    return ItemRead(
        id=item.id,
        name=item.name,
        quantity=display_qty.amount,
        unit=Unit(item.display_unit),
        dimension=Dimension(item.dimension),
        expires_on=item.expires_on,
        version=item.version,
        created_at=item.created_at.isoformat() if item.created_at else "",
        updated_at=item.updated_at.isoformat() if item.updated_at else "",
    )


@router.post("", status_code=201, response_model=ItemRead)
def create_item(
    body: ItemCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    repo = ItemRepository(db)
    item = repo.create(body)
    db.commit()
    db.refresh(item)
    return _item_to_read(item)


@router.get("", response_model=list[ItemRead])
def list_items(
    sort: str = "expires_on",
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ItemRead]:
    repo = ItemRepository(db)
    items = repo.list(sort_by=sort)
    return [_item_to_read(i) for i in items]


@router.post("/sentence/preview", response_model=PantrySentencePreview)
def preview_sentence(
    body: SentenceRequest,
    db: Session = Depends(get_db),  # noqa: B008
    llm: Any = Depends(get_sentence_llm),  # noqa: B008
) -> PantrySentencePreview:
    batch = parse_pantry_sentence(body.sentence, llm)
    return preview_lines(db, body.sentence, batch)


@router.post("/sentence", response_model=list[ItemRead])
def save_sentence(
    body: PantrySentenceCommit,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ItemRead]:
    batch = normalise_draft(DraftPantrySentence(items=body.items))
    try:
        saved = commit_parsed_items(db, batch)
        db.commit()
    except Exception:
        db.rollback()
        raise
    for item in saved:
        db.refresh(item)
    return [_item_to_read(item) for item in saved]


@router.get("/{item_id}", response_model=ItemRead)
def get_item(
    item_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    repo = ItemRepository(db)
    item = repo.get(item_id)
    return _item_to_read(item)


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(
    item_id: str,
    body: ItemUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    repo = ItemRepository(db)
    item = repo.update(item_id, body)
    db.commit()
    db.refresh(item)
    return _item_to_read(item)


@router.post("/{item_id}/merge", response_model=ItemRead)
def merge_item(
    item_id: str,
    body: ItemMerge,
    db: Session = Depends(get_db),  # noqa: B008
) -> ItemRead:
    repo = ItemRepository(db)
    item = repo.add_quantity(item_id, body.quantity, body.unit)
    db.commit()
    db.refresh(item)
    return _item_to_read(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    repo = ItemRepository(db)
    repo.delete(item_id)
    db.commit()
