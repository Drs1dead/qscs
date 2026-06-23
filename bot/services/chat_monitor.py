import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import get_settings
from bot.db.models import Chat, ChatStatus
from bot.db.repositories import ChatRepository, LogRepository, UserRepository
from bot.db.session import async_session_factory

logger = logging.getLogger(__name__)
settings = get_settings()


class ChatMonitorService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("Chat monitor started (interval=%ss)", settings.chat_monitor_interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                await self.check_all_chats()
            except Exception:
                logger.exception("Chat monitor cycle failed")
            await asyncio.sleep(settings.chat_monitor_interval)

    async def check_all_chats(self) -> None:
        async with async_session_factory() as session:
            chat_repo = ChatRepository(session)
            chats = await chat_repo.list_for_monitoring()

        newly_problematic: list[Chat] = []

        for chat in chats:
            if not chat.is_active:
                continue
            status = await self._check_chat(chat)
            if status:
                async with async_session_factory() as session:
                    chat_repo = ChatRepository(session)
                    log_repo = LogRepository(session)
                    await chat_repo.mark_problematic(chat.id, status)
                    await log_repo.add(
                        action="chat_monitor_problem",
                        chat_id=chat.id,
                        details=f"{chat.title}: {status}",
                        is_error=True,
                    )
                chat.status = status
                chat.is_active = False
                newly_problematic.append(chat)
            else:
                try:
                    tg_chat = await self.bot.get_chat(chat.id)
                    async with async_session_factory() as session:
                        chat_repo = ChatRepository(session)
                        await chat_repo.upsert(
                            chat.id,
                            title=tg_chat.title or chat.title,
                            chat_type=tg_chat.type,
                            bot_is_admin=True,
                        )
                except Exception:
                    pass

        if newly_problematic:
            await self._notify_super_admins(newly_problematic)

    async def _check_chat(self, chat: Chat) -> str | None:
        try:
            await self.bot.get_chat(chat.id)
            member = await self.bot.get_chat_member(chat.id, self.bot.id)
            if member.status in ("left", "kicked"):
                return ChatStatus.KICKED.value
            if member.status not in ("administrator", "creator"):
                return ChatStatus.NO_RIGHTS.value
            return None
        except TelegramForbiddenError:
            return ChatStatus.KICKED.value
        except TelegramBadRequest as exc:
            msg = str(exc).lower()
            if "chat not found" in msg or "group chat was deactivated" in msg:
                return ChatStatus.NOT_FOUND.value
            if "kicked" in msg or "not a member" in msg:
                return ChatStatus.KICKED.value
            if "not enough rights" in msg or "have no rights" in msg:
                return ChatStatus.NO_RIGHTS.value
            logger.warning("Chat check bad request chat=%s: %s", chat.id, exc)
            return ChatStatus.NO_RIGHTS.value
        except Exception as exc:
            logger.warning("Chat check failed chat=%s: %s", chat.id, exc)
            return ChatStatus.NOT_FOUND.value

    async def _notify_super_admins(self, chats: list[Chat]) -> None:
        super_ids = set(settings.super_admins)

        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            admins = await user_repo.list_admins(limit=500)
            for admin in admins:
                if admin.is_super_admin:
                    super_ids.add(admin.id)

        if not super_ids:
            logger.warning("No super-admins to notify about problematic chats")
            return

        lines = [
            "⚠️ <b>Обнаружена проблема в чатах!</b>",
            "Бот был удалён или чат не существует.\n",
        ]
        status_labels = {
            ChatStatus.KICKED.value: "удалён из чата",
            ChatStatus.NOT_FOUND.value: "чат не найден",
            ChatStatus.NO_RIGHTS.value: "нет прав администратора",
        }
        for chat in chats:
            label = status_labels.get(chat.status, chat.status)
            lines.append(f"❌ {chat.title} (<code>{chat.id}</code>) — {label}")

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Удалить проблемные чаты из списка",
                        callback_data="admin:delete_problematic",
                    )
                ]
            ]
        )

        for admin_id in super_ids:
            try:
                await self.bot.send_message(admin_id, text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                logger.warning("Failed to notify super-admin %s", admin_id)
