"""Hybrid chat planner: rules first, hosted model only for what rules cannot read.

The model never writes. It returns a ``ChatPlan`` that is checked here, then
run by the same tool dispatch the rules use. Anything wrong with the plan
(timeout, bad schema, missing fields, no open meal) falls back to the rules
reply so no write happens on a doubtful answer.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date
from typing import Any

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ChatPending, ChatThread
from app.db.repositories import ChatRepository, ItemRepository, MealRepository
from app.domain.expiry import is_expired
from app.graph.llm import invoke_structured
from app.schemas.chat import ChatAction, ChatPlan, ChatTool, DraftChatPlan

_log = structlog.get_logger(__name__)

HISTORY_TURNS = 6
HISTORY_CHARS = 280
MEAL_LIMIT = 5

PLANNER_PROMPT = """You are Pip, the planner for a single-user pantry and cooking app.
Read the user's message and the CONTEXT_JSON, then return one ChatPlan.

Rules:
- Choose at most ONE action. Use no action to answer a question or ask for detail.
- Only mention pantry items, quantities, expiry dates, and meals that appear in CONTEXT_JSON.
  Never invent stock. If something is not listed, say it is not in the pantry.
- Items with expired=true are past their date. Say so plainly when they matter.
- Tools: list_pantry, add_items (sentence), update_item (item_name, quantity, unit),
  delete_item (item_name), start_cook (sentence), revise_cook (note), confirm_cook,
  abandon_cook, list_meals, undo_meal, buy_missing (item_name).
- revise_cook, confirm_cook, and abandon_cook need active_cook.present=true.
- Cooking requests, including "use the chicken before it goes off", use start_cook with the
  user's own words as the sentence.
- delete_item, confirm_cook, and undo_meal only ask for confirmation. Reply as a question.
- If CONTEXT_JSON.pending is not null, a yes or no is already being asked. For a question or
  chat, answer in words with no action. Only choose an action when the user clearly asks for it.
- Keep reply to one or two short sentences in plain language. The user may write in any language.
"""

_NEEDS_COOK = {"revise_cook", "confirm_cook", "abandon_cook"}
READ_ONLY_TOOLS: frozenset[str] = frozenset({"list_pantry", "list_meals"})
SUPERSEDES_PENDING: frozenset[str] = frozenset(_NEEDS_COOK)


def build_context(
    db: Session,
    thread: ChatThread,
    pending: ChatPending | None,
    *,
    cook: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Bounded snapshot the planner may read: pantry, meals, open work, recent turns."""
    from app.services.reading import item_to_read

    now = today or date.today()
    pantry = []
    for item in ItemRepository(db).list():
        read = item_to_read(item)
        pantry.append(
            {
                "name": read.name,
                "quantity": format(read.quantity.normalize(), "f"),
                "unit": read.unit.value,
                "expires_on": read.expires_on.isoformat() if read.expires_on else None,
                "expired": is_expired(read.expires_on, today=now),
            }
        )
    meals = [
        {"id": meal.id, "title": meal.title}
        for meal in MealRepository(db).list(status="cooked")[:MEAL_LIMIT]
    ]
    history = [
        {"role": message.role, "text": message.content[:HISTORY_CHARS]}
        for message in ChatRepository(db).messages(thread)[-HISTORY_TURNS - 1 : -1]
    ]
    return {
        "today": now.isoformat(),
        "pantry": pantry,
        "cooked_meals": meals,
        "active_cook_session_id": thread.active_cook_session_id,
        "active_cook": cook or {"present": bool(thread.active_cook_session_id)},
        "pending": None
        if pending is None
        else {"id": pending.id, "kind": pending.kind, "payload": pending.payload},
        "recent_messages": history,
    }


def wants_model(llm: BaseChatModel) -> bool:
    """True when a hosted chef is configured, or a test scripted a ``ChatPlan``."""
    from app.graph.llm import FakeMealModel, llm_mode

    if isinstance(llm, FakeMealModel):
        return any(isinstance(head, (DraftChatPlan, Exception)) for head in llm.script[:1])
    return llm_mode() == "real"


def model_plan(llm: BaseChatModel, text: str, context: dict[str, Any]) -> ChatPlan | None:
    """Ask the model for a plan. ``None`` means use the rules reply instead."""
    messages = [
        SystemMessage(content=PLANNER_PROMPT),
        HumanMessage(
            content=f"CONTEXT_JSON:\n{json.dumps(context, default=str)}\n\nUSER_MESSAGE:\n{text}"
        ),
    ]
    budget = float(settings.chat_planner_timeout or 40)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(invoke_structured, llm, DraftChatPlan, messages)
        raw = future.result(timeout=budget)
    except FutureTimeout:
        _log.warning("chat_planner_timeout", budget=budget)
        return None
    except Exception as exc:
        _log.warning("chat_planner_failed", error=type(exc).__name__)
        return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    try:
        draft = raw if isinstance(raw, DraftChatPlan) else DraftChatPlan.model_validate(raw)
        plan = draft.to_plan()
    except Exception:
        _log.warning("chat_planner_invalid")
        return None
    return checked_plan(plan, text, context)


def checked_plan(plan: ChatPlan, text: str, context: dict[str, Any]) -> ChatPlan | None:
    """Keep one well-formed action, or none. Reject anything the app cannot run."""
    if not plan.actions:
        return plan
    action = plan.actions[0]
    fixed = _complete(action, text)
    if fixed is None:
        return None
    if fixed.tool in _NEEDS_COOK and not context.get("active_cook_session_id"):
        return ChatPlan(
            reply="There is no meal open yet. Ask for one and I can change it.",
            actions=[],
        )
    return ChatPlan(reply=plan.reply, actions=[fixed])


def _complete(action: ChatAction, text: str) -> ChatAction | None:
    tool: ChatTool = action.tool
    if tool in {"add_items"} and not (action.sentence or "").strip():
        return None
    if tool == "start_cook":
        sentence = (action.sentence or "").strip() or text.strip()
        return action.model_copy(update={"sentence": sentence[:300]})
    if tool in {"delete_item", "buy_missing"} and not (action.item_name or "").strip():
        return None
    if tool == "update_item" and (
        not (action.item_name or "").strip() or action.quantity is None or action.quantity <= 0
    ):
        return None
    if tool == "revise_cook":
        note = (action.note or "").strip() or text.strip()
        return action.model_copy(update={"note": note[:300]})
    return action
