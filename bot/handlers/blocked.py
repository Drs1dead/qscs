from aiogram import F, Router
from aiogram.filters import MagicData
from aiogram.types import CallbackQuery, Message

router = Router(name="blocked")


@router.message(F.chat.type.in_({"group", "supergroup", "channel"}))
async def ignore_public_chat_messages(message: Message) -> None:
    pass


@router.message(MagicData(F.access_denied.is_(True)))
async def blocked_message(message: Message) -> None:
    pass


@router.callback_query(MagicData(F.access_denied.is_(True)))
async def blocked_callback(callback: CallbackQuery) -> None:
    pass
