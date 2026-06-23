import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_settings
from bot.db.session import close_db, init_db
from bot.handlers import admin, broadcast, chats, posts, start
from bot.handlers.broadcast import set_broadcast_service
from bot.middlewares.auth import AuthMiddleware
from bot.services.broadcast_service import BroadcastService
from bot.services.chat_monitor import ChatMonitorService
from bot.services.store_service import store_service

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)
settings = get_settings()


async def main() -> None:
    await init_db()
    await store_service.connect()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    broadcast_service = BroadcastService(bot)
    set_broadcast_service(broadcast_service)

    chat_monitor = ChatMonitorService(bot)
    await chat_monitor.start()

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(posts.router)
    dp.include_router(broadcast.router)
    dp.include_router(chats.router)

    logger.info("Bot starting (SQLite + in-memory storage)…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await chat_monitor.stop()
        await close_db()
        await store_service.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
