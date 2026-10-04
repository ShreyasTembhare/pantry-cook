"""Pantry writes shared by the items API and chat."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories import ItemRepository
from app.domain.quick_add import (
    commit_parsed_items,
    normalise_draft,
    parse_pantry_sentence,
    preview_lines,
)
from app.schemas.items import ItemCreate, ItemMerge, ItemRead, ItemUpdate
from app.schemas.quick_add import (
    DraftPantrySentence,
    PantrySentenceCommit,
    PantrySentencePreview,
    SentenceRequest,
)
from app.services.reading import item_to_read


class PantryService:
    def __init__(self, db: Session, llm: Any | None = None) -> None:
        self.db = db
        self.llm = llm
        self.items = ItemRepository(db)

    def create(self, body: ItemCreate) -> ItemRead:
        item = self.items.create(body)
        self.db.commit()
        self.db.refresh(item)
        return item_to_read(item)

    def list(self, sort: str = "expires_on") -> list[ItemRead]:
        return [item_to_read(item) for item in self.items.list(sort_by=sort)]

    def get(self, item_id: str) -> ItemRead:
        return item_to_read(self.items.get(item_id))

    def update(self, item_id: str, body: ItemUpdate) -> ItemRead:
        item = self.items.update(item_id, body)
        self.db.commit()
        self.db.refresh(item)
        return item_to_read(item)

    def merge(self, item_id: str, body: ItemMerge) -> ItemRead:
        item = self.items.add_quantity(item_id, body.quantity, body.unit)
        self.db.commit()
        self.db.refresh(item)
        return item_to_read(item)

    def delete(self, item_id: str) -> None:
        self.items.delete(item_id)
        self.db.commit()

    def preview_sentence(self, body: SentenceRequest) -> PantrySentencePreview:
        batch = parse_pantry_sentence(body.sentence, self.llm)
        return preview_lines(self.db, body.sentence, batch)

    def save_sentence(self, body: PantrySentenceCommit) -> list[ItemRead]:
        batch = normalise_draft(DraftPantrySentence(items=body.items))
        try:
            saved = commit_parsed_items(self.db, batch)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        for item in saved:
            self.db.refresh(item)
        return [item_to_read(item) for item in saved]
