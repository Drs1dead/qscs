import asyncio
from collections import defaultdict

from aiogram.types import Message


class AlbumCollector:
    """Debounced collector for media groups."""

    def __init__(self, delay: float = 1.0) -> None:
        self._delay = delay
        self._buffers: dict[str, list[Message]] = defaultdict(list)
        self._tasks: dict[str, asyncio.Task] = {}

    async def collect(self, message: Message) -> list[Message] | None:
        if not message.media_group_id or not message.from_user:
            return None

        key = f"{message.from_user.id}:{message.media_group_id}"
        self._buffers[key].append(message)

        if key in self._tasks and not self._tasks[key].done():
            return None

        self._tasks[key] = asyncio.create_task(self._flush(key))
        return await self._tasks[key]

    async def _flush(self, key: str) -> list[Message] | None:
        await asyncio.sleep(self._delay)
        messages = self._buffers.pop(key, [])
        self._tasks.pop(key, None)
        if not messages:
            return None
        return sorted(messages, key=lambda m: m.message_id)


album_collector = AlbumCollector()
