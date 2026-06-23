"""In-memory store for broadcast control + SQLite for persistent settings."""

from bot.config import get_settings
from bot.db.repositories import AppSettingRepository
from bot.db.session import async_session_factory

settings = get_settings()
DEFAULT_INTERVAL_KEY = "default_interval"


class StoreService:
    def __init__(self) -> None:
        self._manual_stop_flags: set[int] = set()
        self._active_manual_broadcasts: dict[int, int] = {}

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def set_manual_broadcast_active(self, job_id: int, user_id: int) -> None:
        self._active_manual_broadcasts[user_id] = job_id

    async def get_active_broadcast(self, user_id: int) -> int | None:
        return self._active_manual_broadcasts.get(user_id)

    async def clear_manual_broadcast(self, user_id: int) -> None:
        self._active_manual_broadcasts.pop(user_id, None)

    async def request_manual_stop(self, job_id: int) -> None:
        self._manual_stop_flags.add(job_id)

    async def is_manual_stop_requested(self, job_id: int) -> bool:
        return job_id in self._manual_stop_flags

    async def clear_manual_stop(self, job_id: int) -> None:
        self._manual_stop_flags.discard(job_id)

    async def set_default_interval(self, seconds: int) -> None:
        async with async_session_factory() as session:
            repo = AppSettingRepository(session)
            await repo.set(DEFAULT_INTERVAL_KEY, str(seconds))

    async def get_default_interval(self, fallback: int) -> int:
        async with async_session_factory() as session:
            repo = AppSettingRepository(session)
            value = await repo.get(DEFAULT_INTERVAL_KEY)
        return int(value) if value else fallback


store_service = StoreService()
