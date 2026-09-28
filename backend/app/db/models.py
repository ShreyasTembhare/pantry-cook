from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    quantity_base: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    dimension: Mapped[str] = mapped_column(String, nullable=False)
    display_unit: Mapped[str] = mapped_column(String, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("quantity_base >= 0", name="ck_items_quantity_non_negative"),
        Index("ix_items_expires_on", "expires_on"),
    )

    def __repr__(self) -> str:
        return f"<Item {self.name} ({self.quantity_base} {self.display_unit})>"
