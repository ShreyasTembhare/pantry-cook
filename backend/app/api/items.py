from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Item
from app.db.repositories import ItemRepository
from app.domain.units import Dimension, Quantity, Unit
from app.schemas.items import ItemCreate, ItemRead, ItemUpdate

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


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    repo = ItemRepository(db)
    repo.delete(item_id)
    db.commit()
