"""Structured plan the chef returns before any pantry or cook write."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.units import Unit

ChatRole = Literal["user", "assistant", "system"]
ChatTool = Literal[
    "list_pantry",
    "add_items",
    "update_item",
    "delete_item",
    "start_cook",
    "revise_cook",
    "confirm_cook",
    "abandon_cook",
    "list_meals",
    "undo_meal",
    "buy_missing",
]
PendingKind = Literal["delete_item", "confirm_cook", "undo_meal"]


class ChatAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: ChatTool
    sentence: str | None = None
    item_name: str | None = None
    quantity: Decimal | None = None
    unit: Unit | None = None
    note: str | None = None
    meal_id: str | None = None


class ChatPlan(BaseModel):
    """One turn: a reply the user reads, then zero or more tool calls."""

    model_config = ConfigDict(extra="ignore")

    reply: str = Field(min_length=1, max_length=2000)
    actions: list[ChatAction] = Field(default_factory=list)


class DraftChatAction(BaseModel):
    """Model-facing action. Plain floats keep the JSON schema simple for hosted models."""

    model_config = ConfigDict(extra="ignore")

    tool: ChatTool
    sentence: str | None = None
    item_name: str | None = None
    quantity: float | None = None
    unit: Literal["g", "kg", "ml", "L", "count"] | None = None
    note: str | None = None
    meal_id: str | None = None

    def to_action(self) -> ChatAction:
        return ChatAction(
            tool=self.tool,
            sentence=self.sentence,
            item_name=self.item_name,
            quantity=None if self.quantity is None else Decimal(str(self.quantity)),
            unit=None if self.unit is None else Unit(self.unit),
            note=self.note,
            meal_id=self.meal_id,
        )


class DraftChatPlan(BaseModel):
    """What the planner model returns: a short reply and at most one action."""

    model_config = ConfigDict(extra="ignore")

    reply: str = Field(min_length=1, max_length=2000)
    actions: list[DraftChatAction] = Field(default_factory=list, max_length=3)

    def to_plan(self) -> ChatPlan:
        return ChatPlan(reply=self.reply, actions=[a.to_action() for a in self.actions])


class ChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)


class ChatCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["pantry", "pending", "proposal", "meals", "meal", "error", "note"]
    title: str
    pending_id: str | None = None
    pending_kind: PendingKind | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    proposal: dict[str, Any] | None = None
    cook_session_id: str | None = None
    proposal_etag: str | None = None
    meals: list[dict[str, Any]] = Field(default_factory=list)
    meal: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class ChatMessageRead(BaseModel):
    id: str
    role: ChatRole
    content: str
    cards: list[ChatCard]
    created_at: str


class ChatThreadRead(BaseModel):
    id: str
    active_cook_session_id: str | None
    messages: list[ChatMessageRead]


class ChatTurnRead(BaseModel):
    thread_id: str
    user: ChatMessageRead
    assistant: ChatMessageRead
