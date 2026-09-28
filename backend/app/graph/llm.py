from __future__ import annotations

import json
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from app.config import Settings
from app.config import settings as default_settings
from app.domain.expiry import is_expired
from app.domain.units import Dimension, Quantity, Unit
from app.schemas.llm import Constraints, MealProposal, ProposedMissingLine, ProposedUseLine

_CONTEXT_MARKER = "COOK_CONTEXT_JSON:\n"


class FakeMealModel(BaseChatModel):
    """Offline meal model.

    ``script`` is a queue of structured results (or exceptions / raw strings)
    consumed only when the next item matches the schema being asked for.
    Anything else falls through to the deterministic rules used in dev.
    ``received`` records every prompt so tests can assert what the node sent.
    """

    script: list[Any] = Field(default_factory=list)
    received: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-meal"

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        self.received.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="{}"))])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
        del kwargs

        def _call(messages: Any) -> BaseModel:
            self.received.append(messages)
            if self.script:
                head = self.script[0]
                if isinstance(head, str):
                    self.script.pop(0)
                    raise ValueError(head)
                if isinstance(head, Exception):
                    self.script.pop(0)
                    raise head
                if (
                    isinstance(head, BaseModel)
                    and isinstance(schema, type)
                    and isinstance(head, schema)
                ):
                    self.script.pop(0)
                    return head
            return _rules_for(schema, messages)

        return RunnableLambda(_call)


def get_llm(app_settings: Settings | None = None) -> FakeMealModel:
    """Return the offline model.

    M3 does not call a hosted provider. ``PANTRY_LLM_PROVIDER=fake`` is the
    default, and a real provider without this milestone's wiring stays on the
    fake model so the app boots with no API key.
    """
    cfg = app_settings or default_settings
    if cfg.llm_provider not in {"fake", "real"}:
        return FakeMealModel()
    return FakeMealModel()


def _message_text(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    if isinstance(messages, list):
        parts: list[str] = []
        for message in messages:
            content = getattr(message, "content", message)
            parts.append(content if isinstance(content, str) else str(content))
        return "\n".join(parts)
    content = getattr(messages, "content", None)
    if isinstance(content, str):
        return content
    return str(messages)


def _context_from_messages(messages: Any) -> dict[str, Any]:
    text = _message_text(messages)
    marker = text.find(_CONTEXT_MARKER)
    if marker < 0:
        return {}
    raw = text[marker + len(_CONTEXT_MARKER) :].strip()
    try:
        parsed, _end = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rules_for(schema: Any, messages: Any) -> BaseModel:
    context = _context_from_messages(messages)
    if schema is Constraints:
        return _rules_constraints(context)
    if schema is MealProposal:
        return _rules_proposal(context)
    raise TypeError(f"FakeMealModel cannot fill schema {schema!r}")


def _rules_constraints(context: dict[str, Any]) -> Constraints:
    sentence = str(context.get("sentence") or "")
    pantry = [row for row in context.get("pantry") or [] if isinstance(row, dict)]
    folded = sentence.casefold()

    dietary: list[str] = []
    if "vegan" in folded:
        dietary.append("vegan")
    elif "vegetarian" in folded:
        dietary.append("vegetarian")
    if "gluten-free" in folded or "gluten free" in folded:
        dietary.append("gluten_free")
    if "dairy-free" in folded or "dairy free" in folded:
        dietary.append("dairy_free")
    if "nut-free" in folded or "nut free" in folded:
        dietary.append("nut_free")

    mood = next((name for name in ("warm", "light", "quick") if name in folded), None)

    servings = 2
    match = re.search(r"\bfor\s+(\d+)\b", folded) or re.search(r"\b(\d+)\s+servings?\b", folded)
    if match:
        servings = min(24, max(1, int(match.group(1))))

    max_minutes = None
    minutes = re.search(r"\b(\d+)\s*(?:min|mins|minutes)\b", folded)
    if minutes:
        value = int(minutes.group(1))
        if 5 <= value <= 240:
            max_minutes = value

    must: list[str] = []
    for row in pantry:
        name = str(row.get("name") or "").casefold()
        if name and name in folded:
            must.append(str(row["id"]))

    words = re.findall(r"[a-z0-9']+", folded)
    notes = None
    if len(words) <= 2 and not must and not dietary and mood is None:
        notes = "ambiguous request"

    return Constraints(
        must_use_item_ids=must,
        dietary=dietary,  # type: ignore[arg-type]
        max_minutes=max_minutes,
        servings=servings,
        mood=mood,
        free_text_notes=notes,
    )


def _rules_proposal(context: dict[str, Any]) -> MealProposal:
    sentence = str(context.get("sentence") or "")
    pantry = [row for row in context.get("pantry") or [] if isinstance(row, dict)]
    constraints = context.get("constraints") if isinstance(context.get("constraints"), dict) else {}
    notes = [str(note) for note in (context.get("notes") or [])]
    folded = sentence.casefold()

    try:
        servings = int(constraints.get("servings") or 2)
    except (TypeError, ValueError):
        servings = 2
    servings = min(24, max(1, servings))
    must = {str(item_id) for item_id in constraints.get("must_use_item_ids") or []}
    ambiguous = bool(constraints.get("free_text_notes"))

    def usable(row: dict[str, Any]) -> bool:
        try:
            qty = Decimal(str(row.get("quantity_base") or "0"))
        except Exception:
            return False
        if qty <= 0:
            return False
        named = str(row.get("name") or "").casefold() in folded or str(row.get("id")) in must
        return named or not is_expired(row.get("expires_on"), today=date.today())

    usable_rows = [row for row in pantry if usable(row)]
    must_rows = [row for row in usable_rows if str(row.get("id")) in must]
    others = [row for row in usable_rows if str(row.get("id")) not in must]
    chosen = (must_rows + others)[:3]

    lines: list[ProposedUseLine | ProposedMissingLine] = [_half_line(row) for row in chosen]
    for row in pantry:
        try:
            qty = Decimal(str(row.get("quantity_base") or "0"))
        except Exception:
            continue
        if qty <= 0 and str(row.get("id")) in must:
            lines.append(
                ProposedMissingLine(
                    name=str(row.get("name") or "ingredient"), quantity_note="out of stock"
                )
            )

    owned = " ".join(str(row.get("name") or "").casefold() for row in pantry)
    if "olive oil" not in owned:
        lines.append(ProposedMissingLine(name="olive oil", quantity_note="a splash"))
    if not lines:
        lines.append(ProposedMissingLine(name="olive oil", quantity_note="a splash"))

    names = [str(row.get("name") or "ingredient") for row in chosen]
    title = _title(names)
    if names and ambiguous:
        rationale = "Picked the soonest-expiring items because the request was open-ended."
    elif names:
        rationale = f"Uses the {names[0]} while it is still good."
    else:
        rationale = "Nothing ready to cook is on hand, so this is mostly a shopping list."
    if notes:
        rationale = f"{rationale} Noted: {notes[-1]}."

    fewer = any("fewer steps" in note.casefold() for note in notes)
    if fewer:
        steps = ["Cook everything in one pan and serve."]
    else:
        main = names[0].lower() if names else "what you have"
        steps = [
            f"Prep the {main}.",
            "Cook gently until just done.",
            "Taste, season, and serve.",
        ]

    return MealProposal(
        title=title,
        servings=servings,
        lines=lines,
        steps=steps,
        rationale=rationale,
    )


def _title(names: list[str]) -> str:
    if len(names) >= 2:
        title = f"{names[0]} and {names[1]}"
    elif names:
        title = f"{names[0]} on a plate"
    else:
        title = "Shopping-list supper"
    title = title.strip()
    if len(title) < 3:
        title = "Home plate"
    return title[:80]


def _half_line(row: dict[str, Any]) -> ProposedUseLine:
    unit = Unit(str(row["display_unit"]))
    base = Decimal(str(row["quantity_base"]))
    display = Quantity.from_base(base, Dimension(str(row["dimension"])), unit)
    amount = display.amount
    if unit.dimension == Dimension.COUNT:
        whole = int(amount)
        half = whole // 2
        if half < 1:
            half = whole if whole >= 1 else 1
        qty = Decimal(half)
    else:
        half_amount = (amount / Decimal(2)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if half_amount <= 0 or half_amount > amount:
            half_amount = amount
        qty = half_amount
    return ProposedUseLine(item_id=str(row["id"]), quantity=qty, unit=unit)
