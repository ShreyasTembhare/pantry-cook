import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("PANTRY_LLM_PROVIDER", "fake")
os.environ.setdefault("PANTRY_MAINTENANCE", "0")

from alembic.config import Config

from alembic import command
from app.config import settings

_APP_TABLES = (
    "chat_pending",
    "chat_messages",
    "chat_threads",
    "meal_lines",
    "meals",
    "cook_sessions",
    "items",
)
_CHECKPOINT_TABLES = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)


def _truncate(engine: Engine) -> None:
    with engine.begin() as conn:
        existing = set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        names = [name for name in (*_APP_TABLES, *_CHECKPOINT_TABLES) if name in existing]
        if names:
            conn.execute(text("TRUNCATE " + ", ".join(names) + " RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    """Apply migrations once. Tests then roll back their own writes."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(postgres_engine: Engine) -> Generator[sessionmaker[Session], None, None]:
    """One transaction per test. Commits inside the test are savepoints."""
    _truncate(postgres_engine)
    connection = postgres_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield factory
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
