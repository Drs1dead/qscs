from typing import Any

from aiogram.filters import BaseFilter


class AccessDenied(BaseFilter):
    async def __call__(self, event: Any, data: dict[str, Any]) -> bool:
        return bool(data.get("access_denied"))
