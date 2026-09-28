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
