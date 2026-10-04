from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.domain.errors import DomainError
from app.observability import request_id_var
from app.schemas.problem import FieldError, ProblemDetails

_log = structlog.get_logger()

_PROBLEM_TEXT: dict[int, str] = {
    404: "Not found.",
    409: "The request conflicts with the current pantry.",
    422: "The request failed validation.",
    429: "The chef is rate limited.",
    500: "Unexpected error.",
    502: "The chef could not answer.",
    503: "The database is unavailable.",
    504: "The chef took too long.",
}


def problem_responses(*statuses: int) -> dict[int, dict[str, Any]]:
    """OpenAPI entries for the problem+json statuses a route can return."""
    documented = {*statuses, 500, 503}
    return {
        status: {"model": ProblemDetails, "description": _PROBLEM_TEXT[status]}
        for status in sorted(documented)
    }


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request_id_var.get()


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    problem = ProblemDetails(
        type=f"https://pantrycook.dev/problems/{code}",
        title=code.replace("_", " ").title(),
        status=status,
        detail=detail,
        instance=str(request.url.path),
        code=code,
        request_id=_get_request_id(request),
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def _database_unavailable(exc: BaseException) -> bool:
    if isinstance(exc, (OperationalError, InterfaceError)):
        return True
    return isinstance(exc, DBAPIError) and bool(exc.connection_invalidated)


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    problem = ProblemDetails(
        type=f"https://pantrycook.dev/problems/{exc.code}",
        title=exc.code.replace("_", " ").title(),
        status=exc.status,
        detail=exc.detail,
        instance=str(request.url.path),
        code=exc.code,
        extra=exc.extra or None,
        request_id=_get_request_id(request),
    )
    headers: dict[str, str] = {}
    retry_after = exc.extra.get("retry_after") if exc.code == "llm_rate_limited" else None
    if isinstance(retry_after, int) and retry_after >= 0:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=exc.status,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", [])]
        errors.append(
            FieldError(
                loc=loc,
                msg=err.get("msg", "Validation error"),
                type=err.get("type", "value_error"),
            )
        )

    problem = ProblemDetails(
        type="https://pantrycook.dev/problems/validation_failed",
        title="Validation Failed",
        status=422,
        detail="One or more fields failed validation",
        instance=str(request.url.path),
        code="validation_failed",
        errors=errors,
        request_id=_get_request_id(request),
    )
    return JSONResponse(
        status_code=422,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if _database_unavailable(exc):
        _log.exception("database_unavailable", path=request.url.path)
        return _problem(
            request,
            503,
            "database_unavailable",
            "The database is unavailable.",
        )
    _log.exception("unhandled_error", path=request.url.path)
    return _problem(request, 500, "internal_error", "Something went wrong.")
