"""Turn a chat message into pantry, cook, and meal actions.

The model only fills a ``ChatPlan``. Writes go through the same domain
functions the REST routes use. Delete, cook-confirm, and undo wait on a
pending row until the user confirms.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, ChatPending, ChatThread, Item
from app.db.repositories import ChatRepository, ItemRepository, MealRepository
from app.domain.buy import buy_missing_line
from app.domain.chat_planner import (
    READ_ONLY_TOOLS,
    SUPERSEDES_PENDING,
    build_context,
    model_plan,
    wants_model,
)
from app.domain.errors import DomainError, ItemNotFoundError
from app.domain.units import Unit
from app.schemas.chat import ChatAction, ChatCard, ChatMessageRead, ChatPlan, ChatTurnRead
from app.schemas.items import ItemUpdate, normalise_name_key

MODEL_UNAVAILABLE_REPLY = (
    "I couldn't work that out just now. Try “2 leeks and 500 g chicken”, "
    "“what's in the pantry”, or “something warm for dinner”."
)
_YES = {"yes", "yep", "yeah", "confirm", "do it", "ok", "okay", "sure", "go ahead", "y"}
_NO = {"no", "nope", "cancel", "never mind", "nevermind", "stop", "n", "nah"}
_USE_UP = re.compile(
    r"\buse\b.+\b(?:before (?:it|they|that|this|these|those) (?:goes?|spoils?|expires?)|"
    r"(?:is|are) about to (?:expire|go off|spoil))\b",
    re.I,
)
_ADD_PREFIX = re.compile(r"^(please\s+)?(add|put|save|i have|i've got|we have)\s+", re.I)
_DELETE = re.compile(
    r"\b(?:remove|delete|toss|throw out|get rid of)\s+(?:the\s+|my\s+)?(?P<name>.+)$",
    re.I,
)
_UPDATE = re.compile(
    r"\b(?:change|set|update)\s+(?:the\s+)?(?P<name>.+?)\s+to\s+"
    r"(?P<qty>\d+(?:[.,]\d+)?)(?:\s*(?P<unit>kg|ml|count|g|l))?\s*$",
    re.I,
)
_COOK = re.compile(
    r"\b(cook|recipe|supper|dinner|lunch|breakfast|meal idea)\b|^something\b",
    re.I,
)
_REVISE = re.compile(
    r"\b(fewer steps|more steps|vegetarian|vegan|gluten|quicker|faster|spicier|"
    r"less salt|no meat|lighter|simpler)\b",
    re.I,
)
_BOUGHT = re.compile(r"\bbought\s+(?:the\s+|some\s+)?(?P<name>.+)$", re.I)
_BOUGHT_SIZE = re.compile(
    r"^(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|ml|count|g|l)?\s+(?:of\s+)?(?P<name>[^\d].*)$",
    re.I,
)


def rules_chat_plan(text: str, context: dict[str, Any] | None = None) -> ChatPlan:
    """Offline chef. Used when the provider is fake, and as the demo fallback."""
    raw = text.strip()
    folded = raw.casefold()
    cooking = bool((context or {}).get("active_cook_session_id"))

    if folded.startswith("revise the meal:"):
        note = raw.split(":", 1)[1].strip() or raw
        return ChatPlan(
            reply="I'll adjust the proposal.",
            actions=[ChatAction(tool="revise_cook", note=note[:300])],
        )

    deleted = _DELETE.search(raw)
    if deleted:
        name = deleted.group("name").strip(" .")
        return ChatPlan(
            reply=f"Remove {name} from the pantry?",
            actions=[ChatAction(tool="delete_item", item_name=name)],
        )

    updated = _UPDATE.search(raw)
    if updated:
        unit_token = (updated.group("unit") or "").casefold()
        unit = _unit_token(unit_token) if unit_token else None
        qty = Decimal(updated.group("qty").replace(",", "."))
        return ChatPlan(
            reply=f"Updated {updated.group('name').strip()}.",
            actions=[
                ChatAction(
                    tool="update_item",
                    item_name=updated.group("name").strip(),
                    quantity=qty,
                    unit=unit,
                )
            ],
        )

    if re.search(r"\b(what('s| is) in|in the pantry|list pantry|what do i have)\b", folded):
        return ChatPlan(reply="Here's what's on hand.", actions=[ChatAction(tool="list_pantry")])

    if re.search(r"\b(undo|put back)\b", folded):
        return ChatPlan(
            reply="Put the last meal back in the pantry?",
            actions=[ChatAction(tool="undo_meal")],
        )

    if re.search(r"\b(my meals|what did i cook|cooked meals)\b", folded):
        return ChatPlan(reply="Meals you've cooked.", actions=[ChatAction(tool="list_meals")])

    bought = _BOUGHT.search(raw)
    if bought:
        rest = bought.group("name").strip(" .")
        sized = _BOUGHT_SIZE.match(rest)
        if sized:
            token = (sized.group("unit") or "").casefold()
            return ChatPlan(
                reply=f"I'll mark {sized.group('name').strip()} as bought.",
                actions=[
                    ChatAction(
                        tool="buy_missing",
                        item_name=sized.group("name").strip(" ."),
                        quantity=Decimal(sized.group("qty").replace(",", ".")),
                        unit=_unit_token(token) if token else None,
                    )
                ],
            )
        return ChatPlan(
            reply=f"I'll mark {rest} as bought.",
            actions=[ChatAction(tool="buy_missing", item_name=rest)],
        )

    if re.search(r"\b(abandon|never mind the meal|cancel the meal|skip this)\b", folded):
        return ChatPlan(reply="Leaving that proposal.", actions=[ChatAction(tool="abandon_cook")])

    if _REVISE.search(raw) or (cooking and re.search(r"\b(make it|change it|instead)\b", folded)):
        return ChatPlan(
            reply="I'll adjust the proposal.",
            actions=[ChatAction(tool="revise_cook", note=raw[:300])],
        )

    if re.search(r"\b(looks good|cook it|i'?ll make that|let's cook)\b", folded):
        return ChatPlan(reply="Cook this?", actions=[ChatAction(tool="confirm_cook")])

    if _COOK.search(raw) or _USE_UP.search(raw):
        sentence = raw if len(raw) >= 3 else "something warm"
        return ChatPlan(
            reply="Let me see what we can cook.",
            actions=[ChatAction(tool="start_cook", sentence=sentence)],
        )

    pantry_sentence = _pantry_sentence(raw)
    if pantry_sentence:
        return ChatPlan(
            reply="Adding that to the pantry.",
            actions=[ChatAction(tool="add_items", sentence=pantry_sentence)],
        )

    return ChatPlan(
        reply=(
            "I can add or remove pantry items, suggest a meal, or change a recipe. "
            "Try “2 leeks and 500 g chicken”."
        ),
        actions=[],
    )


def plan_chat(
    db: Session,
    graph: Any,
    llm: BaseChatModel,
    thread: ChatThread,
    pending: ChatPending | None,
    text: str,
) -> ChatPlan:
    """Rules first. The hosted chef only reads what the rules could not.

    Every plan, from either source, runs through the same tool dispatch.
    """
    plan = rules_chat_plan(text, {"active_cook_session_id": thread.active_cook_session_id})
    if plan.actions or not wants_model(llm):
        return plan
    context = _context(db, graph, thread, pending)
    modelled = model_plan(llm, text, context)
    if modelled is not None:
        return modelled
    return ChatPlan(reply=MODEL_UNAVAILABLE_REPLY, actions=[])


def _answer(text: str) -> str | None:
    """Read a short yes or no, ignoring case, punctuation, and a trailing please."""
    words = re.sub(r"[^\w\s]", " ", text.casefold())
    cleaned = " ".join(words.split())
    cleaned = re.sub(r"\s+(please|thanks|thank you)$", "", cleaned)
    if cleaned in _YES:
        return "yes"
    if cleaned in _NO:
        return "no"
    return None


def _pending_label(pending: ChatPending) -> str:
    payload = pending.payload if isinstance(pending.payload, dict) else {}
    if pending.kind == "delete_item":
        return f"remove {payload.get('name') or 'that item'}"
    if pending.kind == "undo_meal":
        return f"undo {payload.get('title') or 'that meal'}"
    return "cook the open meal"


def run_turn(db: Session, graph: Any, llm: BaseChatModel, text: str) -> ChatTurnRead:
    """Append the user message, run one plan, and store the assistant reply."""
    thread = home_thread(db)
    user = _append(db, thread, "user", text.strip(), [])
    db.commit()
    db.refresh(thread)

    answer = _answer(text)
    pending = open_pending(db, thread.id)
    cards: list[ChatCard]
    if pending is not None and answer == "yes":
        reply, cards = confirm_pending(db, graph, thread, pending)
    elif pending is not None and answer == "no":
        reply, cards = cancel_pending(db, pending)
    else:
        try:
            plan = plan_chat(db, graph, llm, thread, pending, text)
        except Exception as exc:
            from app.graph.nodes import LlmCallError

            if not isinstance(exc, LlmCallError):
                raise
            reply = exc.detail
            cards = [_error_card(DomainError(exc.code, 504, exc.detail, exc.extra))]
        else:
            reply = plan.reply
            cards = []
            first = plan.actions[0].tool if plan.actions else None
            if pending is not None and first is not None and first not in READ_ONLY_TOOLS:
                if first in SUPERSEDES_PENDING:
                    ChatRepository(db).cancel_open(thread.id)
                else:
                    plan = ChatPlan(
                        reply=f"Say yes or no first: should I {_pending_label(pending)}?",
                        actions=[],
                    )
                    reply = plan.reply
            for action in plan.actions:
                cards.extend(_run_action(db, graph, llm, thread, action))

    assistant = _append(db, thread, "assistant", reply, cards)
    db.commit()
    db.refresh(user)
    db.refresh(assistant)
    return ChatTurnRead(
        thread_id=thread.id,
        user=_read_message(user),
        assistant=_read_message(assistant),
    )


def confirm_pending(
    db: Session,
    graph: Any,
    thread: ChatThread,
    pending: ChatPending,
    *,
    acknowledge_expired: bool = False,
) -> tuple[str, list[ChatCard]]:
    """Run a staged delete, cook confirm, or undo."""
    payload = pending.payload if isinstance(pending.payload, dict) else {}
    try:
        if pending.kind == "delete_item":
            item_id = str(payload.get("item_id") or "")
            name = str(payload.get("name") or "that item")
            ItemRepository(db).delete(item_id)
            card = ChatCard(type="pantry", title=f"Removed {name}.", items=[])
            reply = f"Removed {name}."
        elif pending.kind == "confirm_cook":
            card, reply = _confirm_cook(db, graph, thread, payload, acknowledge_expired)
        elif pending.kind == "undo_meal":
            card, reply = _undo(db, str(payload.get("meal_id") or ""))
        else:
            raise DomainError("pending_unknown", 422, "That confirmation is not supported.")
    except DomainError as exc:
        db.rollback()
        return exc.detail, [_error_card(exc)]

    pending.status = "confirmed"
    db.flush()
    return reply, [card]


def cancel_pending(db: Session, pending: ChatPending) -> tuple[str, list[ChatCard]]:
    pending.status = "cancelled"
    db.flush()
    return "Left that as it was.", []


def home_thread(db: Session) -> ChatThread:
    return ChatRepository(db).home_thread()


def open_pending(db: Session, thread_id: str) -> ChatPending | None:
    return ChatRepository(db).open_pending(thread_id)


def thread_messages(db: Session, thread: ChatThread) -> list[ChatMessage]:
    return ChatRepository(db).messages(thread)


def _run_action(
    db: Session,
    graph: Any,
    llm: BaseChatModel,
    thread: ChatThread,
    action: ChatAction,
) -> list[ChatCard]:
    try:
        card = _dispatch(db, graph, llm, thread, action)
        db.commit()
        return [card]
    except DomainError as exc:
        db.rollback()
        return [_error_card(exc)]


def _dispatch(
    db: Session,
    graph: Any,
    llm: BaseChatModel,
    thread: ChatThread,
    action: ChatAction,
) -> ChatCard:
    if action.tool == "list_pantry":
        items = [_item_json(item) for item in ItemRepository(db).list()]
        title = "The pantry is empty." if not items else "In the pantry"
        return ChatCard(type="pantry", title=title, items=items)

    if action.tool == "add_items":
        return _add_items(db, llm, action.sentence or "")

    if action.tool == "update_item":
        return _update_item(db, action)

    if action.tool == "delete_item":
        return _stage_delete(db, thread, action.item_name or "")

    if action.tool == "start_cook":
        return _start_cook(db, graph, thread, action.sentence or "")

    if action.tool == "revise_cook":
        return _revise(db, graph, thread, action.note or "")

    if action.tool == "confirm_cook":
        return _stage_confirm_cook(db, graph, thread)

    if action.tool == "abandon_cook":
        return _abandon(db, graph, thread)

    if action.tool == "list_meals":
        meals = MealRepository(db).list(status="cooked")
        from app.services.reading import meal_to_list_item

        dumped = [meal_to_list_item(meal).model_dump(mode="json") for meal in meals]
        title = "No cooked meals yet." if not dumped else "Cooked meals"
        return ChatCard(type="meals", title=title, meals=dumped)

    if action.tool == "undo_meal":
        return _stage_undo(db, thread, action.meal_id)

    if action.tool == "buy_missing":
        return _buy(db, action)

    raise DomainError("unknown_tool", 422, "I don't know how to do that.")


def _add_items(db: Session, llm: BaseChatModel, sentence: str) -> ChatCard:
    from app.domain.quick_add import commit_parsed_items, parse_pantry_sentence

    batch = parse_pantry_sentence(sentence, llm)
    saved = commit_parsed_items(db, batch)
    db.flush()
    return ChatCard(
        type="pantry",
        title="Added to the pantry.",
        items=[_item_json(item) for item in saved],
    )


def _update_item(db: Session, action: ChatAction) -> ChatCard:
    item = _item_named(db, action.item_name or "")
    unit = action.unit or Unit(item.display_unit)
    if action.quantity is None:
        raise DomainError("quantity_required", 422, "Say how much to set it to.")
    updated = ItemRepository(db).update(
        item.id,
        ItemUpdate(quantity=action.quantity, unit=unit, version=item.version),
    )
    return ChatCard(
        type="pantry",
        title=f"Updated {updated.name}.",
        items=[_item_json(updated)],
    )


def _stage_delete(db: Session, thread: ChatThread, name: str) -> ChatCard:
    item = _item_named(db, name)
    pending = _stage(
        db,
        thread,
        "delete_item",
        {"item_id": item.id, "name": item.name},
    )
    return ChatCard(
        type="pending",
        title=f"Remove {item.name}?",
        pending_id=pending.id,
        pending_kind="delete_item",
        items=[_item_json(item)],
    )


def _start_cook(db: Session, graph: Any, thread: ChatThread, sentence: str) -> ChatCard:
    from app.schemas.cook import CookStartRequest
    from app.services.cook import CookService

    session = CookService(db, graph).start(CookStartRequest(sentence=sentence.strip()))
    thread.active_cook_session_id = session.id
    db.flush()
    proposal = session.proposal.model_dump(mode="json") if session.proposal else None
    title = session.proposal.title if session.proposal else "Working on a meal"
    return ChatCard(
        type="proposal",
        title=title,
        proposal=proposal,
        cook_session_id=session.id,
        proposal_etag=session.proposal_etag,
    )


def _revise(db: Session, graph: Any, thread: ChatThread, note: str) -> ChatCard:
    from app.schemas.cook import CookReviseRequest
    from app.services.cook import CookService

    session_id = _active_cook_id(thread)
    session = CookService(db, graph).revise(session_id, CookReviseRequest(note=note.strip()[:300]))
    proposal = session.proposal.model_dump(mode="json") if session.proposal else None
    title = session.proposal.title if session.proposal else "Revised"
    return ChatCard(
        type="proposal",
        title=title,
        proposal=proposal,
        cook_session_id=session.id,
        proposal_etag=session.proposal_etag,
    )


def _stage_confirm_cook(db: Session, graph: Any, thread: ChatThread) -> ChatCard:
    from app.services.cook import CookService

    session_id = _active_cook_id(thread)
    session = CookService(db, graph).get(session_id)
    if session.proposal is None or not session.proposal_etag:
        raise DomainError("session_not_awaiting", 409, "There is no meal waiting to cook.")
    pending = _stage(
        db,
        thread,
        "confirm_cook",
        {
            "cook_session_id": session.id,
            "proposal_etag": session.proposal_etag,
        },
    )
    return ChatCard(
        type="pending",
        title="Cook this?",
        pending_id=pending.id,
        pending_kind="confirm_cook",
        proposal=session.proposal.model_dump(mode="json"),
        cook_session_id=session.id,
        proposal_etag=session.proposal_etag,
    )


def _confirm_cook(
    db: Session,
    graph: Any,
    thread: ChatThread,
    payload: dict[str, Any],
    acknowledge_expired: bool,
) -> tuple[ChatCard, str]:
    from app.schemas.cook import CookConfirmRequest
    from app.services.cook import CookService

    session_id = str(payload.get("cook_session_id") or thread.active_cook_session_id or "")
    etag = str(payload.get("proposal_etag") or "")
    meal = CookService(db, graph).confirm(
        session_id,
        CookConfirmRequest(proposal_etag=etag, acknowledge_expired=acknowledge_expired),
    )
    thread.active_cook_session_id = None
    card = ChatCard(
        type="meal",
        title=meal.title,
        meal=meal.model_dump(mode="json"),
    )
    return card, f"Cooked {meal.title}."


def _abandon(db: Session, graph: Any, thread: ChatThread) -> ChatCard:
    from app.services.cook import CookService

    session_id = _active_cook_id(thread)
    CookService(db, graph).abandon(session_id)
    thread.active_cook_session_id = None
    return ChatCard(type="note", title="Proposal set aside.")


def _stage_undo(db: Session, thread: ChatThread, meal_id: str | None) -> ChatCard:
    from app.services.reading import meal_to_read

    if meal_id:
        meal = MealRepository(db).get(meal_id)
    else:
        meals = MealRepository(db).list(status="cooked")
        if not meals:
            raise DomainError("meal_not_found", 404, "There is no cooked meal to undo.")
        meal = meals[0]
    pending = _stage(db, thread, "undo_meal", {"meal_id": meal.id, "title": meal.title})
    return ChatCard(
        type="pending",
        title=f"Undo {meal.title}?",
        pending_id=pending.id,
        pending_kind="undo_meal",
        meal=meal_to_read(meal).model_dump(mode="json"),
    )


def _undo(db: Session, meal_id: str) -> tuple[ChatCard, str]:
    from app.domain.commit import undo_cooked_meal
    from app.services.reading import meal_to_read

    meal = undo_cooked_meal(db, meal_id)
    db.flush()
    read = meal_to_read(meal)
    return (
        ChatCard(type="meal", title=f"Undid {read.title}.", meal=read.model_dump(mode="json")),
        f"Undid {read.title}.",
    )


def _buy(db: Session, action: ChatAction) -> ChatCard:
    from app.services.reading import meal_to_read

    name = (action.item_name or "").casefold()
    if not name:
        raise DomainError("missing_name", 422, "Which ingredient did you buy?")
    meals = MealRepository(db).list(status=None)
    for meal in meals:
        for line in meal.lines:
            label = (line.missing_name or "").casefold()
            if line.kind == "missing" and name in label:
                bought = buy_missing_line(
                    db,
                    meal.id,
                    line.id,
                    quantity=action.quantity,
                    unit=action.unit,
                )
                db.flush()
                return ChatCard(
                    type="meal",
                    title=f"Added {bought.item.name} to the pantry.",
                    meal=meal_to_read(bought.meal).model_dump(mode="json"),
                )
    raise DomainError("meal_line_not_found", 404, f"Nothing on a shopping list matches {name}.")


def _stage(db: Session, thread: ChatThread, kind: str, payload: dict[str, object]) -> ChatPending:
    return ChatRepository(db).stage(thread.id, kind, payload)


def _item_named(db: Session, name: str) -> Item:
    repo = ItemRepository(db)
    found = repo.find_by_name_key(normalise_name_key(name))
    if found is not None:
        return found
    folded = name.casefold().strip()
    matches = [
        item
        for item in repo.list()
        if folded and (folded in item.name.casefold() or item.name.casefold() in folded)
    ]
    if len(matches) == 1:
        return matches[0]
    raise ItemNotFoundError(name)


def _item_json(item: Item) -> dict[str, Any]:
    from app.services.reading import item_to_read

    return item_to_read(item).model_dump(mode="json")


def _active_cook_id(thread: ChatThread) -> str:
    if not thread.active_cook_session_id:
        raise DomainError(
            "session_not_awaiting",
            409,
            "Start a meal first, then I can change or confirm it.",
        )
    return thread.active_cook_session_id


def _append(
    db: Session,
    thread: ChatThread,
    role: str,
    content: str,
    cards: list[ChatCard],
) -> ChatMessage:
    message = ChatMessage(
        thread_id=thread.id,
        role=role,
        content=content,
        cards=[card.model_dump(mode="json") for card in cards],
    )
    db.add(message)
    db.flush()
    return message


def _read_message(message: ChatMessage) -> ChatMessageRead:
    raw_cards = message.cards if isinstance(message.cards, list) else []
    cards = [ChatCard.model_validate(card) for card in raw_cards if isinstance(card, dict)]
    created = message.created_at.isoformat() if message.created_at else ""
    return ChatMessageRead(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        cards=cards,
        created_at=created,
    )


def _error_card(exc: DomainError) -> ChatCard:
    return ChatCard(
        type="error",
        title=exc.detail,
        error={"code": exc.code, "detail": exc.detail, **exc.extra},
    )


def _context(
    db: Session,
    graph: Any,
    thread: ChatThread,
    pending: ChatPending | None,
) -> dict[str, Any]:
    return build_context(db, thread, pending, cook=_cook_summary(db, graph, thread))


def _cook_summary(db: Session, graph: Any, thread: ChatThread) -> dict[str, Any]:
    """Title and ingredient names of the open proposal, or ``present: false``."""
    session_id = thread.active_cook_session_id
    if not session_id or graph is None:
        return {"present": False}
    from app.services.cook import CookService

    try:
        session = CookService(db, graph).get(session_id)
    except Exception:
        return {"present": False}
    proposal = session.proposal
    if proposal is None:
        return {"present": True, "status": session.status}
    names = {item.id: item.name for item in ItemRepository(db).list()}
    uses = [names.get(line.item_id, "an item") for line in proposal.lines if line.kind == "use"]
    missing = [line.name for line in proposal.lines if line.kind == "missing"]
    return {
        "present": True,
        "status": session.status,
        "title": proposal.title,
        "uses": uses,
        "missing": missing,
    }


def _pantry_sentence(raw: str) -> str | None:
    stripped = _ADD_PREFIX.sub("", raw).strip()
    if len(stripped) < 3 or not re.search(r"\d", stripped):
        return None
    if _COOK.search(stripped) or _DELETE.search(stripped):
        return None
    return stripped


def _unit_token(token: str) -> Unit:
    return {
        "g": Unit.G,
        "kg": Unit.KG,
        "ml": Unit.ML,
        "l": Unit.L,
        "count": Unit.COUNT,
    }[token]
