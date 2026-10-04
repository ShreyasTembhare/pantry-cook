from __future__ import annotations

import contextvars
import difflib
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Item
from app.db.repositories import ItemRepository
from app.domain.commit import commit_cooked_meal
from app.domain.errors import DomainError
from app.domain.expiry import is_expired
from app.domain.units import Dimension, Quantity, Unit
from app.graph.llm import llm_mode
from app.graph.prompts import EXPIRING_COOK_NOTE, PARSE_SYSTEM, PROPOSE_SYSTEM
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
_NODE_WALL_SECONDS = 60.0
_log = structlog.get_logger()


class StructuredOutputError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class LlmCallError(Exception):
    def __init__(self, code: str, detail: str, extra: dict[str, Any] | None = None) -> None:
        self.code = code
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


def _llm_payload(exc: LlmCallError) -> dict[str, Any]:
    return {"code": exc.code, "detail": exc.detail, **exc.extra}


def _log_node(node: str, state: CookState, started: float, **fields: Any) -> None:
    from app.observability import request_id_var

    model = "fake" if llm_mode() == "fake" else settings.llm_model
    _log.info(
        "cook_node",
        request_id=request_id_var.get() or None,
        session_id=state.get("session_id"),
        node=node,
        attempt=len(state.get("attempts") or []),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        llm_model=model,
        tokens_in=fields.get("tokens_in"),
        tokens_out=fields.get("tokens_out"),
    )


def load_pantry(state: CookState, session_factory: SessionFactory) -> dict[str, Any]:
    """Read the pantry soonest-expiry first, null expiries last, then name."""
    db = session_factory()
    try:
        items = ItemRepository(db).list(sort_by="expires_on")
        return {"pantry_snapshot": [_row_from_item(item) for item in items], "error": None}
    finally:
        db.close()


def parse_sentence(state: CookState, llm: BaseChatModel) -> dict[str, Any]:
    """Turn the sentence into constraints.

    A blank sentence skips the model and pins the meal to the three pantry
    items that expire soonest. A written sentence still goes through the model.
    """
    if not str(state.get("sentence") or "").strip():
        started = time.perf_counter()
        constraints = constraints_for_expiring(list(state.get("pantry_snapshot") or []))
        result = {"constraints": constraints.model_dump(mode="json"), "error": None}
        _log_node("parse_sentence", state, started)
        return result

    messages = [
        SystemMessage(content=PARSE_SYSTEM),
        HumanMessage(content=_context_message(state)),
    ]
    started = time.perf_counter()
    result = _structured_or_llm(
        llm,
        Constraints,
        messages,
        on_ok=lambda constraints: {
            "constraints": constraints.model_dump(mode="json"),
            "error": None,
        },
        on_invalid=lambda exc: {
            "error": {
                "code": "llm_output_invalid",
                "detail": "The proposal came back garbled.",
                "cause": exc.detail,
            }
        },
        on_llm_error=lambda exc: {"error": _llm_payload(exc)},
    )
    _log_node("parse_sentence", state, started)
    return result


def propose_meal(state: CookState, llm: BaseChatModel) -> dict[str, Any]:
    messages = [
        SystemMessage(content=PROPOSE_SYSTEM),
        HumanMessage(content=_context_message(state)),
    ]
    started = time.perf_counter()
    try:
        proposal = _structured_or_llm_value(llm, MealProposal, messages)
    except StructuredOutputError as exc:
        result = {
            "proposal": None,
            "error": {
                "code": "llm_output_invalid",
                "detail": "The proposal came back garbled.",
                "cause": exc.detail,
            },
        }
    except LlmCallError as exc:
        result = {"proposal": None, "error": _llm_payload(exc)}
    else:
        result = {"proposal": proposal.model_dump(mode="json"), "error": None}
    _log_node("propose_meal", state, started)
    return result


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


def constraints_for_expiring(
    snapshot: list[dict[str, Any]], *, today: date | None = None, limit: int = 3
) -> Constraints:
    """Constraints that prefer the soonest-expiring food still worth cooking.

    Expired rows and empty jars are skipped. Items with no date are not forced
    in; the propose step can still use them when nothing is dated.
    """
    chosen = _soonest_expiring(snapshot, today=today or date.today(), limit=limit)
    return Constraints(
        must_use_item_ids=[str(row["id"]) for row in chosen],
        servings=2,
        free_text_notes=EXPIRING_COOK_NOTE,
    )


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


def _soonest_expiring(
    snapshot: list[dict[str, Any]], *, today: date, limit: int
) -> list[dict[str, Any]]:
    ranked: list[tuple[date, str, str, dict[str, Any]]] = []
    for row in snapshot:
        expires = _expiry_on(row.get("expires_on"))
        if expires is None or is_expired(expires, today=today):
            continue
        if _base_quantity(row) <= 0:
            continue
        ranked.append(
            (expires, str(row.get("name") or "").casefold(), str(row.get("id") or ""), row)
        )
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [row for _expires, _name, _item_id, row in ranked[:limit]]


def _expiry_on(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _base_quantity(row: dict[str, Any]) -> Decimal:
    try:
        return Decimal(str(row.get("quantity_base") or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


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


def classify_llm_exception(exc: BaseException) -> dict[str, Any] | None:
    """Map a provider error onto a cook error code. Schema mistakes return None."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    name = type(exc).__name__.lower().replace("_", "")
    if isinstance(exc, TimeoutError) or "timeout" in name or status in {408, 504}:
        return {"code": "llm_timeout", "detail": "The chef took too long."}
    if status == 429 or "ratelimit" in name:
        extra: dict[str, Any] = {}
        retry_after = _retry_after(exc)
        if retry_after is not None:
            extra["retry_after"] = retry_after
        return {
            "code": "llm_rate_limited",
            "detail": "The kitchen is busy. Try again in a moment.",
            "extra": extra,
        }
    if status in {401, 403} or "authentication" in name or "permissiondenied" in name:
        _log.error("llm_auth_failed", error_type=type(exc).__name__)
        return {"code": "llm_unavailable", "detail": "Can't reach the chef right now."}
    return None


def _retry_after(exc: BaseException) -> int | None:
    raw = getattr(exc, "retry_after", None)
    headers = getattr(exc, "headers", None)
    if raw is None and headers is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) if response is not None else None
    if raw is None and headers is not None and hasattr(headers, "get"):
        raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        value = int(float(str(raw)))
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _structured_or_llm_value(
    llm: BaseChatModel,
    schema: type[BaseModel],
    messages: list[Any],
) -> BaseModel:
    """Call the model. The offline chef applies its own rules when nothing is scripted."""
    return _invoke_structured(llm, schema, messages)


def _structured_or_llm(
    llm: BaseChatModel,
    schema: type[BaseModel],
    messages: list[Any],
    *,
    on_ok: Callable[[BaseModel], dict[str, Any]],
    on_invalid: Callable[[StructuredOutputError], dict[str, Any]],
    on_llm_error: Callable[[LlmCallError], dict[str, Any]],
) -> dict[str, Any]:
    try:
        value = _structured_or_llm_value(llm, schema, messages)
    except StructuredOutputError as exc:
        return on_invalid(exc)
    except LlmCallError as exc:
        return on_llm_error(exc)
    return on_ok(value)


def _invoke_once(llm: BaseChatModel, schema: type[BaseModel], messages: list[Any]) -> Any:
    try:
        return llm.with_structured_output(schema).invoke(messages)
    except LlmCallError:
        raise
    except Exception as exc:
        classified = classify_llm_exception(exc)
        if classified is None:
            raise
        raise LlmCallError(
            str(classified["code"]),
            str(classified["detail"]),
            classified.get("extra") if isinstance(classified.get("extra"), dict) else None,
        ) from exc


def _invoke_structured(
    llm: BaseChatModel,
    schema: type[BaseModel],
    messages: list[Any],
    *,
    wall_seconds: float | None = None,
) -> Any:
    """Call the model, retrying schema mistakes. Timeouts and 429s are not retried.

    The node gives up after ``wall_seconds`` even if the client is still retrying.
    """
    if wall_seconds is None:
        wall_seconds = max(_NODE_WALL_SECONDS, float(settings.llm_timeout or 30) + 30.0)
    deadline = time.monotonic() + wall_seconds
    last = "The model returned nothing."
    current = list(messages)
    for _ in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LlmCallError("llm_timeout", "The chef took too long.")
        pool = ThreadPoolExecutor(max_workers=1)
        context = contextvars.copy_context()
        try:
            future = pool.submit(context.run, _invoke_once, llm, schema, current)
            try:
                result = future.result(timeout=remaining)
                if result is None:
                    raise ValueError("empty structured output")
                if isinstance(result, schema):
                    return result
                return schema.model_validate(result)
            except TimeoutError:
                raise LlmCallError("llm_timeout", "The chef took too long.") from None
            except LlmCallError:
                raise
            except Exception as exc:
                last = str(exc)
                current = [
                    *messages,
                    HumanMessage(content="your last output was not valid JSON matching the schema"),
                ]
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    raise StructuredOutputError(last)
