import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import domain_error_handler, validation_error_handler
from app.config import settings
from app.domain.errors import DomainError
from app.domain.sessions import SWEEP_INTERVAL_SECONDS
from app.observability import RequestIdMiddleware, configure_logging, configure_tracing

_log = structlog.get_logger()


def _maintain_sessions() -> None:
    from app.api.deps import get_graph
    from app.db.engine import SessionLocal
    from app.domain.sessions import run_session_maintenance

    db = SessionLocal()
    try:
        run_session_maintenance(db, get_graph())
        db.commit()
    except Exception:
        db.rollback()
        _log.exception("session_maintenance_failed")
    finally:
        db.close()


def _maintenance_enabled() -> bool:
    flag = os.environ.get("PANTRY_MAINTENANCE", "1").strip().lower()
    return flag not in {"0", "false", "off", "no"}


async def _maintenance_loop(stop: asyncio.Event) -> None:
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=SWEEP_INTERVAL_SECONDS)
        except TimeoutError:
            await asyncio.to_thread(_maintain_sessions)
            continue
        return


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    from app.api.deps import close_graph, init_graph
    from app.db.engine import engine
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    init_graph()
    stop = asyncio.Event()
    task: asyncio.Task[None] | None = None
    if _maintenance_enabled():
        await asyncio.to_thread(_maintain_sessions)
        task = asyncio.create_task(_maintenance_loop(stop))
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        close_graph()


def create_app() -> FastAPI:
    configure_logging()
    configure_tracing()
    app = FastAPI(
        title="Pantry Cook",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    from app.api.cook import router as cook_router
    from app.api.cook_stream import router as cook_stream_router
    from app.api.health import router as health_router
    from app.api.items import router as items_router
    from app.api.meals import router as meals_router

    app.include_router(health_router)
    app.include_router(items_router)
    app.include_router(cook_router)
    app.include_router(cook_stream_router)
    app.include_router(meals_router)

    return app


app = create_app()
