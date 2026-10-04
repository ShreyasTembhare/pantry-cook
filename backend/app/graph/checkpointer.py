"""Postgres checkpointer for cook invoke and the cook SSE stream.

``PostgresSaver`` implements the sync checkpoint API. The cook stream calls
the async methods, which the library leaves unimplemented, so those methods
run the sync ones on a worker thread. The saver's own lock keeps that single
connection to one caller at a time.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import dict_row

from app.db.engine import psycopg_conninfo


class PostgresCookSaver(PostgresSaver):
    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,  # noqa: A002
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        checkpoints = await asyncio.to_thread(
            self._list_checkpoints,
            config,
            filter,
            before,
            limit,
        )
        for checkpoint in checkpoints:
            yield checkpoint

    def _list_checkpoints(
        self,
        config: RunnableConfig | None,
        metadata_filter: dict[str, Any] | None,
        before: RunnableConfig | None,
        limit: int | None,
    ) -> list[CheckpointTuple]:
        return list(self.list(config, filter=metadata_filter, before=before, limit=limit))

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)


def open_postgres_saver(database_url: str) -> PostgresCookSaver:
    """Open one autocommit connection and ensure the checkpoint tables exist."""
    conn = Connection.connect(
        psycopg_conninfo(database_url),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )
    saver = PostgresCookSaver(conn)
    saver.setup()
    return saver
