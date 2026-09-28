"""Abandoned-proposal sweep and startup reconcile."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.db.repositories import CookSessionRepository
from app.domain.sessions import (
    heal_if_running,
    reconcile_running_sessions,
    sweep_expired_sessions,
)


class _Graph:
    def __init__(self, snapshot: object) -> None:
        self.snapshot = snapshot
        self.checkpointer = None

    def get_state(self, config: dict[str, object]) -> object:
        del config
        if isinstance(self.snapshot, Exception):
            raise self.snapshot
        return self.snapshot


class _Deleter:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


def _running(db_session: Session, *, updated_at: datetime) -> str:
    row = CookSessionRepository(db_session).create("something warm with the leeks")
    row.status = "running"
    row.updated_at = updated_at
    row.created_at = updated_at
    db_session.commit()
    return row.id


class TestReconcile:
    def test_old_run_without_an_interrupt_is_failed(self, db_session: Session) -> None:
        moment = datetime(2026, 9, 28, 12, 0, 0)
        session_id = _running(db_session, updated_at=moment - timedelta(minutes=11))
        graph = _Graph(SimpleNamespace(values={}, next=(), tasks=()))

        changed = reconcile_running_sessions(db_session, graph, now=moment)

        row = CookSessionRepository(db_session).get(session_id)
        assert changed == 1
        assert row.status == "failed"
        assert row.last_error is not None
        assert row.last_error["code"] == "interrupted_by_restart"

    def test_a_recent_run_is_left_alone(self, db_session: Session) -> None:
        moment = datetime(2026, 9, 28, 12, 0, 0)
        session_id = _running(db_session, updated_at=moment - timedelta(minutes=2))
        graph = _Graph(SimpleNamespace(values={}, next=(), tasks=()))

        reconcile_running_sessions(db_session, graph, now=moment)

        assert CookSessionRepository(db_session).get(session_id).status == "running"

    def test_an_interrupt_is_resumed_as_awaiting(self, db_session: Session) -> None:
        moment = datetime(2026, 9, 28, 12, 0, 0)
        session_id = _running(db_session, updated_at=moment - timedelta(minutes=30))
        graph = _Graph(
            SimpleNamespace(
                values={"attempts": [{}], "proposal": {"title": "Leek soup"}},
                next=("await_user",),
                tasks=(),
            )
        )

        reconcile_running_sessions(db_session, graph, now=moment)

        row = CookSessionRepository(db_session).get(session_id)
        assert row.status == "awaiting_user"
        assert row.attempt_count == 1
        assert row.last_error is None

    def test_unreadable_checkpoint_is_failed(self, db_session: Session) -> None:
        moment = datetime(2026, 9, 28, 12, 0, 0)
        session_id = _running(db_session, updated_at=moment)
        graph = _Graph(RuntimeError("schema changed"))

        reconcile_running_sessions(db_session, graph, now=moment)

        row = CookSessionRepository(db_session).get(session_id)
        assert row.status == "failed"
        assert row.last_error is not None
        assert row.last_error["code"] == "checkpoint_unreadable"
        assert row.last_error["cause"] == "RuntimeError"

    def test_get_path_marks_an_unreadable_checkpoint(self, db_session: Session) -> None:
        session_id = _running(db_session, updated_at=datetime(2026, 9, 28, 12, 0, 0))
        row = CookSessionRepository(db_session).get(session_id)
        heal_if_running(row, _Graph(RuntimeError("gone")))
        assert row.status == "failed"
        assert row.last_error is not None
        assert row.last_error["code"] == "checkpoint_unreadable"


class TestSweep:
    def test_expired_awaiting_sessions_are_abandoned_and_old_threads_deleted(
        self, db_session: Session
    ) -> None:
        moment = datetime(2026, 9, 28, 12, 0, 0)
        fresh = CookSessionRepository(db_session).create("keep this one")
        fresh.status = "awaiting_user"
        fresh.expires_at = moment + timedelta(hours=2)

        stale = CookSessionRepository(db_session).create("drop this one")
        stale.status = "awaiting_user"
        stale.expires_at = moment - timedelta(minutes=1)

        old = CookSessionRepository(db_session).create("already finished")
        old.status = "committed"
        old.updated_at = moment - timedelta(days=8)
        db_session.commit()

        deleter = _Deleter()
        abandoned, deleted = sweep_expired_sessions(db_session, deleter, now=moment)
        db_session.commit()

        assert abandoned == 1
        assert deleted == 1
        assert deleter.deleted == [old.id]
        assert CookSessionRepository(db_session).get(fresh.id).status == "awaiting_user"
        assert CookSessionRepository(db_session).get(stale.id).status == "abandoned"

    def test_a_just_abandoned_session_keeps_its_checkpoint(self, db_session: Session) -> None:
        moment = datetime(2026, 9, 28, 12, 0, 0)
        row = CookSessionRepository(db_session).create("waiting")
        row.status = "awaiting_user"
        row.expires_at = moment - timedelta(hours=1)
        db_session.commit()

        deleter = _Deleter()
        abandoned, deleted = sweep_expired_sessions(db_session, deleter, now=moment)

        assert abandoned == 1
        assert deleted == 0
        assert deleter.deleted == []
