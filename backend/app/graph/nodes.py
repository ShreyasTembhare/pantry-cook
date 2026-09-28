from __future__ import annotations

import difflib
import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db.models import Item
from app.db.repositories import ItemRepository
from app.domain.commit import commit_cooked_meal
from app.domain.errors import DomainError
from app.domain.expiry import is_expired
from app.domain.units import Dimension, Quantity, Unit
from app.graph.prompts import PARSE_SYSTEM, PROPOSE_SYSTEM
from app.graph.state import MAX_AUTO_REPAIR, MAX_TOTAL_ATTEMPTS, CookState
from app.schemas.cook import ResumePayload
from app.schemas.llm import (
    Constraints,
    MealProposal,
    PantryRow,
    ProposedUseLine,
    Violation,
)

SessionFactory = Callable[[], Session]
_CONTEXT_MARKER = "COOK_CONTEXT_JSON:\n"


class StructuredOutputError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def load_pantry(state: CookState, session_factory: SessionFactory) -> dict[str, Any]:
    """Read the pantry soonest-expiry first, null expiries last, then name."""
    db = session_factory()
    try:
        items = ItemRepository(db).list(sort_by="expires_on")
        return {"pantry_snapshot": [_row_from_item(item) for item in items], "error": None}
    finally:
        db.close()


def parse_sentence(state: CookState, llm: BaseChatModel) -> dict[str, Any]:
    messages = [
        SystemMessage(content=PARSE_SYSTEM),
        HumanMessage(content=_context_message(state)),
    ]
    try:
        constraints = _invoke_structured(llm, Constraints, messages)
    except StructuredOutputError as exc:
        return {
            "error": {
                "code": "llm_output_invalid",
                "detail": "The proposal came back garbled.",
                "cause": exc.detail,
            }
        }
    return {"constraints": constraints.model_dump(mode="json"), "error": None}


def propose_meal(state: CookState, llm: BaseChatModel) -> dict[str, Any]:
    messages = [
        SystemMessage(content=PROPOSE_SYSTEM),
        HumanMessage(content=_context_message(state)),
    ]
    try:
        proposal = _invoke_structured(llm, MealProposal, messages)
    except StructuredOutputError as exc:
        return {
            "proposal": None,
            "error": {
                "code": "llm_output_invalid",
                "detail": "The proposal came back garbled.",
                "cause": exc.detail,
            },
        }
    return {"proposal": proposal.model_dump(mode="json"), "error": None}


def validate_proposal(state: CookState) -> dict[str, Any]:
    """Pure check of the latest proposal against the pantry snapshot."""
    raw = state.get("proposal")
    if not raw:
        return {
            "error": {
                "code": "llm_output_invalid",
                "detail": "The proposal came back garbled.",
            }
        }
    proposal = MealProposal.model_validate(raw)
    snapshot = list(state.get("pantry_snapshot") or [])
    found = find_violations(proposal, snapshot)
    dumped = [violation.model_dump(mode="json") for violation in found]

    trigger = state.get("next_trigger") or "initial"
    notes = list(state.get("user_notes") or [])
    user_note = notes[-1] if trigger == "user_revision" and notes else None
    attempt_no = len(state.get("attempts") or []) + 1
    attempt = {
        "attempt_no": attempt_no,
        "trigger": trigger,
        "user_note": user_note,
        "proposal": raw,
        "validation_errors": dumped,
    }

    error: dict[str, Any] | None = None
    repair_used = int(state.get("repair_used") or 0)
    next_trigger = trigger
    if found:
        repair_used += 1
        if attempt_no >= MAX_TOTAL_ATTEMPTS:
            error = {
                "code": "too_many_attempts",
                "detail": "This one isn't converging.",
                "violations": dumped,
            }
        elif repair_used >= MAX_AUTO_REPAIR:
            error = {
                "code": "could_not_satisfy",
                "detail": "Couldn't fit a meal to your pantry after 3 tries.",
                "violations": dumped,
            }
        else:
            next_trigger = "auto_repair"
    else:
        repair_used = 0

    return {
        "violations": dumped,
        "attempts": [attempt],
        "repair_used": repair_used,
        "next_trigger": next_trigger,
        "error": error,
    }


def await_user(state: CookState) -> dict[str, Any]:
    from langgraph.types import interrupt

    resume = interrupt(
        {
            "proposal": state.get("proposal"),
            "attempt": len(state.get("attempts") or []),
        }
    )
    try:
        payload = ResumePayload.model_validate(resume)
    except ValidationError as exc:
        return {
            "decision": None,
            "error": {
                "code": "invalid_resume",
                "detail": "The resume payload was not valid.",
                "cause": str(exc),
            },
        }
    if payload.decision == "revise":
        return {
            "decision": "revise",
            "user_notes": [payload.note or ""],
            "repair_used": 0,
            "next_trigger": "user_revision",
            "violations": [],
            "error": None,
        }
    if payload.decision == "abandon":
        return {"decision": "abandon", "error": None}
    return {"decision": "confirm", "error": None}


def commit_meal(state: CookState, session_factory: SessionFactory) -> dict[str, Any]:
    db = session_factory()
    try:
        meal = commit_cooked_meal(
            db,
            proposal=state["proposal"] or {},
            snapshot=list(state.get("pantry_snapshot") or []),
            sentence=state["sentence"],
            cook_session_id=state["session_id"],
        )
        db.commit()
        return {
            "result": {"meal_id": meal.id, "title": meal.title},
            "error": None,
        }
    except DomainError as exc:
        db.rollback()
        error: dict[str, Any] = {
            "code": exc.code,
            "detail": exc.detail,
            **exc.extra,
        }
        return {"result": None, "error": error}
    finally:
        db.close()


def fail(state: CookState) -> dict[str, Any]:
    """Terminal marker for a cook that could not produce a confirmable proposal."""
    del state
    return {}


def find_violations(proposal: MealProposal, snapshot: list[dict[str, Any]]) -> list[Violation]:
    by_id = {str(row["id"]): row for row in snapshot}
    violations: list[Violation] = []
    use_lines = [line for line in proposal.lines if isinstance(line, ProposedUseLine)]
    requested: dict[str, Decimal] = {}

    for line in use_lines:
        row = by_id.get(line.item_id)
        if row is None:
            hint = _suggest_item(line.item_id, snapshot)
            if hint is not None:
                message = (
                    f"Unknown item {line.item_id}. Did you mean {hint['id']} ({hint['name']})?"
                )
            else:
                message = f"Unknown item {line.item_id}. Make it a missing line."
            violations.append(Violation(code="unknown_item", message=message, item_id=line.item_id))
            continue
        if line.unit.dimension.value != row["dimension"]:
            violations.append(
                Violation(
                    code="dimension_mismatch",
                    message=(
                        f"{row['name']} is measured in {row['dimension']}, "
                        f"not {line.unit.dimension.value}."
                    ),
                    item_id=line.item_id,
                    detail={"dimension": row["dimension"], "unit": line.unit.value},
                )
            )
            continue
        if (
            line.unit.dimension == Dimension.COUNT
            and line.quantity != line.quantity.to_integral_value()
        ):
            violations.append(
                Violation(
                    code="non_integer_count",
                    message=(
                        f"Counts must be whole numbers (asked for {line.quantity} {row['name']})."
                    ),
                    item_id=line.item_id,
                    detail={"quantity": str(line.quantity)},
                )
            )
            continue
        base = Quantity(line.quantity, line.unit).to_base().amount
        requested[line.item_id] = requested.get(line.item_id, Decimal("0")) + base

    for item_id, amount in requested.items():
        row = by_id[item_id]
        available = Quantity(
            Decimal(str(row["quantity_base"])),
            Unit(str(row["display_unit"])).base_unit,
        ).amount
        if amount > available:
            violations.append(
                Violation(
                    code="insufficient_quantity",
                    message=(
                        f"Wanted {amount} base units of {row['name']} "
                        f"but only {available} are available."
                    ),
                    item_id=item_id,
                    detail={"requested": str(amount), "available": str(available)},
                )
            )

    if _has_usable_item(snapshot) and not use_lines:
        violations.append(
            Violation(
                code="no_pantry_use",
                message="Use at least one pantry item that is still good.",
            )
        )
    return violations


def rows_for_prompt(snapshot: list[dict[str, Any]], sentence: str) -> list[dict[str, Any]]:
    """Drop zero-quantity rows unless the sentence names them.

    The full snapshot stays in state so validation and commit can still see
    those rows. The model only sees food it can actually cook, plus anything
    the user mentioned (so an empty jar can become a missing line).
    """
    folded = sentence.casefold()
    visible: list[dict[str, Any]] = []
    for row in snapshot:
        quantity = Decimal(str(row.get("quantity_base") or "0"))
        named = str(row.get("name") or "").casefold() in folded
        if quantity <= 0 and not named:
            continue
        visible.append(
            {
                **row,
                "expired": is_expired(row.get("expires_on"), today=date.today()),
            }
        )
    return visible


def _has_usable_item(snapshot: list[dict[str, Any]]) -> bool:
    today = date.today()
    for row in snapshot:
        quantity = Decimal(str(row.get("quantity_base") or "0"))
        if quantity <= 0:
            continue
        if is_expired(row.get("expires_on"), today=today):
            continue
        return True
    return False


def _suggest_item(token: str, snapshot: list[dict[str, Any]]) -> dict[str, Any] | None:
    names = [(str(row["name"]).casefold(), row) for row in snapshot]
    match = difflib.get_close_matches(
        token.casefold(), [name for name, _row in names], n=1, cutoff=0.9
    )
    if not match:
        return None
    for name, row in names:
        if name == match[0]:
            return row
    return None


def _row_from_item(item: Item) -> dict[str, Any]:
    row = PantryRow(
        id=item.id,
        name=item.name,
        quantity_base=Decimal(str(item.quantity_base)),
        dimension=Dimension(item.dimension),
        display_unit=Unit(item.display_unit),
        expires_on=item.expires_on,
        version=item.version,
    )
    return row.model_dump(mode="json")


def _context_message(state: CookState) -> str:
    snapshot = list(state.get("pantry_snapshot") or [])
    context = {
        "sentence": state.get("sentence") or "",
        "pantry": rows_for_prompt(snapshot, str(state.get("sentence") or "")),
        "constraints": state.get("constraints"),
        "violations": state.get("violations") or [],
        "notes": state.get("user_notes") or [],
    }
    return _CONTEXT_MARKER + json.dumps(context, sort_keys=True, default=str)


def _invoke_structured(llm: BaseChatModel, schema: type[BaseModel], messages: list[Any]) -> Any:
    last = "The model returned nothing."
    current = list(messages)
    for _ in range(3):
        try:
            result = llm.with_structured_output(schema).invoke(current)
            if result is None:
                raise ValueError("empty structured output")
            if isinstance(result, schema):
                return result
            return schema.model_validate(result)
        except Exception as exc:
            last = str(exc)
            current = [
                *messages,
                HumanMessage(content="your last output was not valid JSON matching the schema"),
            ]
    raise StructuredOutputError(last)
