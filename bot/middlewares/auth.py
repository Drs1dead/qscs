from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import get_settings
from bot.db.repositories import UserRepository
from bot.db.session import async_session_factory

settings = get_settings()


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is None:
            return await handler(event, data)

        # Chat membership updates must always pass through
        if event.__class__.__name__ == "ChatMemberUpdated":
            return await handler(event, data)

        is_super = user.id in settings.super_admins

        async with async_session_factory() as session:
            repo = UserRepository(session)
            db_user = await repo.get(user.id)
            if db_user is None and is_super:
                db_user = await repo.upsert(
                    user.id,
                    username=user.username,
                    full_name=user.full_name,
                    is_super_admin=True,
                )
            if db_user is None or not db_user.is_active:
                if isinstance(event, CallbackQuery):
                    await event.answer("⛔ Нет доступа", show_alert=True)
                    return True
                if isinstance(event, Message) and event.text and event.text.startswith("/"):
                    await event.answer("⛔ У вас нет доступа к этому боту.")
                    return True
                return True

            data["db_user"] = db_user
            data["is_super_admin"] = db_user.is_super_admin or is_super

        return await handler(event, data)
