from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import domain_error_handler, validation_error_handler
from app.config import settings
from app.domain.errors import DomainError
from app.observability import RequestIdMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    from app.api.deps import close_graph, init_graph
    from app.db.engine import engine
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    init_graph()
    yield
    close_graph()


def create_app() -> FastAPI:
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
