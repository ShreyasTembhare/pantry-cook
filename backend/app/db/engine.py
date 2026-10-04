from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def psycopg_conninfo(database_url: str) -> str:
    """LangGraph's Postgres saver speaks libpq URLs, not the SQLAlchemy driver prefix."""
    prefix = "postgresql+psycopg://"
    if database_url.startswith(prefix):
        return "postgresql://" + database_url.removeprefix(prefix)
    return database_url


def get_engine(database_url: str | None = None) -> Engine:
    return create_engine(
        database_url or settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
