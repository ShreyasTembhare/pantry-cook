import os
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("PANTRY_LLM_PROVIDER", "fake")

from app.db.models import Base


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create a fresh SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=True) as f:
        url = f"sqlite:///{f.name}"
        engine = create_engine(url)

        def set_pragmas(dbapi_conn: object, _rec: object) -> None:
            cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        event.listen(engine, "connect", set_pragmas)
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = session_factory()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
