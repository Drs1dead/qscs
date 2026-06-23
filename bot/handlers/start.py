import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db.models import User
from bot.keyboards.inline import main_menu_keyboard
from bot.utils.formatters import format_main_menu

router = Router(name="start")
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, is_super_admin: bool) -> None:
    await message.answer(
        format_main_menu(is_super_admin),
        reply_markup=main_menu_keyboard(is_super_admin=is_super_admin),
        parse_mode="HTML",
    )


@router.message(Command("debug"))
async def cmd_debug(message: Message, db_user: User) -> None:
    await message.answer(
        f"<b>Debug</b>\n"
        f"User: <code>{db_user.id}</code>\n"
        f"Super: {db_user.is_super_admin}\n"
        f"Active: {db_user.is_active}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, is_super_admin: bool) -> None:
    await callback.message.edit_text(
        format_main_menu(is_super_admin),
        reply_markup=main_menu_keyboard(is_super_admin=is_super_admin),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:close")
async def cb_close_menu(callback: CallbackQuery) -> None:
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
