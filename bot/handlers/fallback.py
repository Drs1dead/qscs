import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db.models import User
from bot.filters.access import AccessDenied
from bot.keyboards.inline import main_menu_keyboard
from bot.utils.formatters import format_main_menu

router = Router(name="fallback")
logger = logging.getLogger(__name__)


@router.callback_query(AccessDenied())
async def blocked_callback(callback: CallbackQuery) -> None:
    pass


@router.message(AccessDenied())
async def blocked_message(message: Message) -> None:
    pass


@router.message(F.chat.type.in_({"group", "supergroup", "channel"}))
async def ignore_public_chat_messages(message: Message) -> None:
    """Bot is added to chats/channels; incoming messages there are ignored."""
    pass


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    logger.info("Unknown callback from user %s: %r", callback.from_user.id, callback.data)
    await callback.answer("Кнопка устарела. Отправьте /start", show_alert=True)


@router.message(F.chat.type == "private")
async def unknown_private_message(message: Message, db_user: User, is_super_admin: bool) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer("Неизвестная команда. Отправьте /start для меню.")
        return
    logger.debug("Unhandled private message from %s: %s", db_user.id, message.content_type)
    await message.answer(
        format_main_menu(is_super_admin),
        reply_markup=main_menu_keyboard(is_super_admin=is_super_admin),
        parse_mode="HTML",
    )
