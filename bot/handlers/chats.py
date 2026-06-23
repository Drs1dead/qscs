from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import get_settings
from bot.db.repositories import ChatRepository
from bot.db.session import async_session_factory
from bot.keyboards.inline import chats_list_keyboard, settings_keyboard
from bot.utils.formatters import format_chats_page
from bot.utils.pagination import paginate

router = Router(name="chats")
settings = get_settings()


@router.my_chat_member()
async def on_bot_membership(event) -> None:
    chat = event.chat
    new = event.new_chat_member
    is_admin = new.status in ("administrator", "creator")

    async with async_session_factory() as session:
        repo = ChatRepository(session)
        if is_admin:
            await repo.upsert(
                chat.id,
                title=chat.title or chat.full_name or "Без названия",
                chat_type=chat.type,
                bot_is_admin=True,
            )
        else:
            await repo.deactivate(chat.id)


@router.callback_query(F.data.startswith("chat:list:"))
async def cb_chat_list(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = ChatRepository(session)
        total = await repo.count_active()
        page, total_pages, offset = paginate(total, page, settings.chats_per_page)
        chats = await repo.list_active(offset=offset, limit=settings.chats_per_page)

    await callback.message.edit_text(
        format_chats_page(chats, page, total_pages, total),
        reply_markup=chats_list_keyboard(page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chat:refresh:"))
async def cb_chat_refresh(callback: CallbackQuery, bot: Bot) -> None:
    page = int(callback.data.split(":")[-1])
    count = 0
    try:
        async for dialog in bot.get_dialogs(limit=500):
            chat = dialog.chat
            if chat.type not in ("group", "supergroup", "channel"):
                continue
            member = await bot.get_chat_member(chat.id, bot.id)
            if member.status in ("administrator", "creator"):
                async with async_session_factory() as session:
                    repo = ChatRepository(session)
                    await repo.upsert(
                        chat.id,
                        title=chat.title or "Без названия",
                        chat_type=chat.type,
                        bot_is_admin=True,
                    )
                count += 1
    except Exception:
        pass

    async with async_session_factory() as session:
        repo = ChatRepository(session)
        total = await repo.count_active()
        page, total_pages, offset = paginate(total, page, settings.chats_per_page)
        chats = await repo.list_active(offset=offset, limit=settings.chats_per_page)

    await callback.message.edit_text(
        format_chats_page(chats, page, total_pages, total) + f"\n\n🔄 Синхронизировано: {count}",
        reply_markup=chats_list_keyboard(page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer("Список обновлён")


@router.callback_query(F.data == "settings:main")
async def cb_settings(callback: CallbackQuery) -> None:
    from bot.services.store_service import store_service

    interval = await store_service.get_default_interval(settings.default_interval)
    await callback.message.edit_text(
        "⚙️ <b>Глобальные настройки</b>",
        reply_markup=settings_keyboard(interval),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings:interval")
async def cb_settings_interval(callback: CallbackQuery) -> None:
    from bot.keyboards.inline import interval_keyboard

    await callback.message.edit_text(
        "⏱ <b>Интервал по умолчанию</b>\n<i>Применяется к постам без индивидуального интервала</i>",
        reply_markup=interval_keyboard(0),
        parse_mode="HTML",
    )
    await callback.answer()
