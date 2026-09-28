import os
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("PANTRY_LLM_PROVIDER", "fake")
os.environ.setdefault("PANTRY_MAINTENANCE", "0")

from app.db.models import Base


def _sqlite_engine(path: str) -> object:
    engine = create_engine(f"sqlite:///{path}")

    def set_pragmas(dbapi_conn: object, _rec: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine, "connect", set_pragmas)
    return engine


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    """Fresh SQLite file and session factory for one test."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=True) as handle:
        engine = _sqlite_engine(handle.name)
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            yield factory
        finally:
            engine.dispose()


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Create a fresh SQLite database for each test."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
