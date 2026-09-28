"""File checkpointer that also serves ``graph.astream``.

``SqliteSaver`` serializes its connection with a lock, but its async methods
raise ``NotImplementedError``. The cook stream calls those methods. This
subclass runs the sync methods on a worker thread, so one connection serves
both ``invoke`` and ``astream``.
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
from langgraph.checkpoint.sqlite import SqliteSaver


class StreamingSqliteSaver(SqliteSaver):
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
