from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    errors: list[FieldError] | None = None
    extra: dict[str, Any] | None = None
    request_id: str
