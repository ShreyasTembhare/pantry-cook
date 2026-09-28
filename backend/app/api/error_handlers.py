from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError
from app.observability import request_id_var
from app.schemas.problem import FieldError, ProblemDetails


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request_id_var.get()


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
