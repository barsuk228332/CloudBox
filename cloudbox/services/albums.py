from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

AlbumKey = tuple[int, int]
FlushCallback = Callable[[list["UploadSummary"]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class UploadSummary:
    record_id: int
    name: str
    size: int
    kind: str
    duplicate: bool
    folder_id: int | None
    folder_label: str


class AlbumBuffer:
    """Собирает файлы одного альбома, чтобы отправить одно подтверждение."""

    def __init__(self, delay: float = 1.0) -> None:
        self._delay = delay
        self._items: dict[AlbumKey, list[UploadSummary]] = {}
        self._tasks: dict[AlbumKey, asyncio.Task[None]] = {}

    def add(self, key: AlbumKey, summary: UploadSummary, flush: FlushCallback) -> None:
        self._items.setdefault(key, []).append(summary)
        old_task = self._tasks.pop(key, None)
        if old_task is not None:
            old_task.cancel()
        self._tasks[key] = asyncio.create_task(self._flush_later(key, flush))

    async def _flush_later(self, key: AlbumKey, flush: FlushCallback) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return

        items = self._items.pop(key, [])
        self._tasks.pop(key, None)
        if not items:
            return
        try:
            await flush(items)
        except Exception:
            logger.exception("Не удалось отправить подтверждение альбома")

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        self._items.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
