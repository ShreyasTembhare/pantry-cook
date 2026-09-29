from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import RunnableConfig
from pydantic import BaseModel, Field, PrivateAttr

from app.config import Settings
from app.config import settings as default_settings
from app.domain.expiry import is_expired
from app.domain.units import Dimension, Quantity, Unit
from app.graph.prompts import EXPIRING_COOK_NOTE
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
    _stream_payload: str = PrivateAttr(default="")
    _echoing: bool = PrivateAttr(default=False)

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
        if not self._echoing:
            self.received.append(messages)
        text = self._stream_payload or "{}"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Yield the scripted proposal so graph ``messages`` mode can see tokens."""
        del messages, stop, run_manager, kwargs
        text = self._stream_payload or "{}"
        step = 36
        for index in range(0, len(text), step):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[index : index + step]))

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
        del kwargs

        def _call(messages: Any, config: RunnableConfig | None = None) -> BaseModel:
            self.received.append(messages)
            result = _next_scripted(self, schema, messages)
            if schema is MealProposal:
                self._stream_payload = result.model_dump_json()
                self._echoing = True
                try:
                    # LangGraph's messages handler turns this into proposal tokens.
                    self.invoke(messages, config)
                finally:
                    self._echoing = False
                    self._stream_payload = ""
            return result

        return RunnableLambda(_call)


def _next_scripted(model: FakeMealModel, schema: Any, messages: Any) -> BaseModel:
    if model.script:
        head = model.script[0]
        if isinstance(head, str):
            model.script.pop(0)
            raise ValueError(head)
        if isinstance(head, Exception):
            model.script.pop(0)
            raise head
        if isinstance(head, BaseModel) and isinstance(schema, type) and isinstance(head, schema):
            model.script.pop(0)
            return head
    return _rules_for(schema, messages)


def llm_mode(app_settings: Settings | None = None) -> str:
    """Effective chef: ``real`` only when config asks for it and a key is set."""
    cfg = app_settings or default_settings
    provider = (cfg.llm_provider or "auto").strip().lower()
    if provider == "fake":
        return "fake"
    if _has_provider_key(cfg):
        return "real"
    return "fake"


def get_llm(app_settings: Settings | None = None) -> BaseChatModel:
    """Return ``init_chat_model`` when a provider key is set, else the offline chef.

    The model id (``openai:gpt-4o-mini`` by default) is configuration. There is
    no per-vendor branch. ``PANTRY_LLM_PROVIDER=fake`` always stays offline so
    tests and the demo chef do not call a hosted model.
    """
    cfg = app_settings or default_settings
    if llm_mode(cfg) == "fake":
        return FakeMealModel()
    key = cfg.openai_api_key.strip()
    if key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = key
    model = (cfg.llm_model or "openai:gpt-4o-mini").strip() or "openai:gpt-4o-mini"
    return _init_chat_model(model, temperature=0, timeout=30, max_retries=2)


def _init_chat_model(model: str, **kwargs: Any) -> BaseChatModel:
    from langchain.chat_models import init_chat_model

    chat = init_chat_model(model, **kwargs)
    if not isinstance(chat, BaseChatModel):
        raise TypeError(f"init_chat_model({model!r}) did not return a chat model")
    return chat


def _has_provider_key(cfg: Settings) -> bool:
    candidates = (
        cfg.openai_api_key,
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("ANTHROPIC_API_KEY", ""),
        os.environ.get("GOOGLE_API_KEY", ""),
    )
    return any(value.strip() for value in candidates)


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
    raw_constraints = context.get("constraints")
    constraints: dict[str, Any] = raw_constraints if isinstance(raw_constraints, dict) else {}
    notes = [str(note) for note in (context.get("notes") or [])]
    folded = sentence.casefold()

    try:
        servings = int(constraints.get("servings") or 2)
    except (TypeError, ValueError):
        servings = 2
    servings = min(24, max(1, servings))
    must_ids = [str(item_id) for item_id in constraints.get("must_use_item_ids") or []]
    must = set(must_ids)
    note = str(constraints.get("free_text_notes") or "")
    expiry_cook = note == EXPIRING_COOK_NOTE
    ambiguous = bool(note)

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
    by_id = {str(row.get("id")): row for row in usable_rows}
    if expiry_cook:
        must_rows = [by_id[item_id] for item_id in must_ids if item_id in by_id]
    else:
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
    if names and expiry_cook:
        rationale = f"Uses {_name_list(names)} before they go off."
    elif names and ambiguous:
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


def _name_list(names: list[str]) -> str:
    lowered = [name.lower() for name in names if name]
    if len(lowered) <= 1:
        return f"the {lowered[0]}" if lowered else "what's on hand"
    if len(lowered) == 2:
        return f"the {lowered[0]} and {lowered[1]}"
    return f"the {', '.join(lowered[:-1])}, and {lowered[-1]}"


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
