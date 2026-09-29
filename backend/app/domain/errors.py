from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for all domain errors, mapped to RFC 9457 Problem Details."""

    def __init__(
        self,
        code: str,
        status: int,
        detail: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.status = status
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


class ItemNotFoundError(DomainError):
    def __init__(self, item_id: str) -> None:
        super().__init__(
            code="item_not_found",
            status=404,
            detail=f"Item {item_id} not found",
            extra={"item_id": item_id},
        )


class DuplicateItemError(DomainError):
    def __init__(self, name: str, existing_id: str) -> None:
        super().__init__(
            code="duplicate_item",
            status=409,
            detail=f"An item named '{name}' already exists",
            extra={"existing_id": existing_id},
        )


class StaleVersionError(DomainError):
    def __init__(self, item_id: str, expected: int, actual: int) -> None:
        super().__init__(
            code="stale_version",
            status=409,
            detail="The item was modified by another request",
            extra={"item_id": item_id, "expected_version": expected, "actual_version": actual},
        )


class EmptyPantryError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="empty_pantry",
            status=409,
            detail="The pantry is empty. Add items before cooking.",
        )


class MealNotFoundError(DomainError):
    def __init__(self, meal_id: str) -> None:
        super().__init__(
            code="meal_not_found",
            status=404,
            detail=f"Meal {meal_id} not found",
            extra={"meal_id": meal_id},
        )


class MealNotCookedError(DomainError):
    def __init__(self, status: str) -> None:
        super().__init__(
            code="meal_not_cooked",
            status=409,
            detail="Only a cooked meal can be undone.",
            extra={"status": status},
        )


class UndoConflictError(DomainError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            code="undo_conflict",
            status=409,
            detail=detail,
        )


class SessionNotFoundError(DomainError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            code="session_not_found",
            status=404,
            detail=f"Cook session {session_id} not found",
            extra={"session_id": session_id},
        )


class SessionNotAwaitingError(DomainError):
    def __init__(self, status: str) -> None:
        super().__init__(
            code="session_not_awaiting",
            status=409,
            detail=f"This cook session is {status} and cannot take that action.",
            extra={"status": status},
        )


class SessionBusyError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="session_busy",
            status=409,
            detail="This cook session is already running.",
        )


class StaleProposalError(DomainError):
    def __init__(
        self,
        changed_item_ids: list[str] | None = None,
        *,
        reason: str = "pantry_changed",
    ) -> None:
        extra: dict[str, Any] = {"reason": reason}
        if changed_item_ids is not None:
            extra["changed_item_ids"] = changed_item_ids
        if reason == "proposal_etag_mismatch":
            detail = "This proposal is out of date. Reload it and try again."
        else:
            detail = "Your pantry changed since this was proposed."
        super().__init__(
            code="stale_proposal",
            status=409,
            detail=detail,
            extra=extra,
        )
        self.changed_item_ids = list(changed_item_ids or [])


class UnitDimensionMismatchError(DomainError):
    def __init__(self, item_dimension: str, unit_dimension: str) -> None:
        super().__init__(
            code="unit_dimension_mismatch",
            status=422,
            detail="That unit is a different kind of measure from the item.",
            extra={"item_dimension": item_dimension, "unit_dimension": unit_dimension},
        )


class QuantityLimitError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="quantity_limit",
            status=422,
            detail="That would put the quantity over the limit.",
        )


class ExpiredUnacknowledgedError(DomainError):
    def __init__(self, items: list[dict[str, Any]]) -> None:
        names = ", ".join(str(item.get("name") or "an item") for item in items)
        super().__init__(
            code="expired_unacknowledged",
            status=409,
            detail=(
                f"This proposal uses expired food ({names}). Confirm you still want to cook it."
            ),
            extra={"expired_items": items},
        )


class InsufficientQuantityError(DomainError):
    def __init__(self, item_id: str, requested: str, available: str) -> None:
        super().__init__(
            code="insufficient_quantity",
            status=409,
            detail="The proposal asks for more than the pantry holds.",
            extra={"item_id": item_id, "requested": requested, "available": available},
        )


class CookFailedError(DomainError):
    def __init__(self, error: dict[str, Any]) -> None:
        code = str(error.get("code") or "cook_failed")
        if code == "llm_timeout":
            status = 504
        elif code == "llm_rate_limited":
            status = 429
        elif code.startswith("llm_"):
            status = 502
        else:
            status = 422
        detail = str(error.get("detail") or "The cook session failed.")
        super().__init__(code=code, status=status, detail=detail, extra=error)
