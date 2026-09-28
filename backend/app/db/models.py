from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    sentence: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    servings: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="cooked")
    cook_session_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    cooked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    lines: Mapped[list[MealLine]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        order_by="MealLine.position",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("servings >= 1 AND servings <= 24", name="ck_meals_servings"),
        CheckConstraint(
            "status IN ('proposed', 'cooked', 'undone')",
            name="ck_meals_status",
        ),
        Index("ix_meals_created_at", "created_at"),
    )


class MealLine(Base):
    __tablename__ = "meal_lines"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    meal_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    item_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_name_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    quantity_base: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimension: Mapped[str | None] = mapped_column(String, nullable=True)
    display_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    missing_name: Mapped[str | None] = mapped_column(String, nullable=True)
    missing_note: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    meal: Mapped[Meal] = relationship(back_populates="lines")

    __table_args__ = (
        CheckConstraint("kind IN ('use', 'missing')", name="ck_meal_lines_kind"),
        CheckConstraint(
            "quantity_base IS NULL OR quantity_base >= 0",
            name="ck_meal_lines_quantity_non_negative",
        ),
        Index("ix_meal_lines_meal_id", "meal_id"),
    )


class CookSession(Base):
    __tablename__ = "cook_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    sentence: Mapped[str] = mapped_column(String, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    meal_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("meals.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'awaiting_user', 'committed', 'abandoned', 'failed')",
            name="ck_cook_sessions_status",
        ),
        Index("ix_cook_sessions_status_expires_at", "status", "expires_at"),
    )
