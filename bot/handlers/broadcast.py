import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.config import get_settings
from bot.db.models import User
from bot.db.repositories import ChatRepository, PostRepository
from bot.db.session import async_session_factory
from bot.keyboards.inline import broadcast_confirm_keyboard, broadcast_progress_keyboard
from bot.services.broadcast_service import BroadcastService
from bot.services.store_service import store_service
from bot.utils.formatters import format_interval

router = Router(name="broadcast")
logger = logging.getLogger(__name__)
settings = get_settings()

_broadcast_service: BroadcastService | None = None


def set_broadcast_service(service: BroadcastService) -> None:
    global _broadcast_service
    _broadcast_service = service


@router.callback_query(F.data.startswith("broadcast:confirm:"))
async def cb_broadcast_confirm(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        chat_repo = ChatRepository(session)
        post_repo = PostRepository(session)
        post = await post_repo.get(post_id)
        total = await chat_repo.count_active()
        excluded = len(post.excluded_chats) if post else 0

    if post is None:
        await callback.answer("Пост не найден", show_alert=True)
        return

    target = total - excluded
    interval = post.interval_seconds or await store_service.get_default_interval(settings.default_interval)

    if post.send_mode == "copy":
        mode_text = "✏️ <b>Copy</b> — можно добавить подпись"
        if post.copy_caption:
            mode_text += f"\n└─ Подпись: {post.copy_caption[:80]}"
    else:
        mode_text = "🔄 <b>Forward</b> — Premium-эмодзи сохраняются"

    await callback.message.edit_text(
        f"🚀 <b>Размножение поста #{post_id}</b>\n\n"
        f"└─ Чатов: <b>{target}</b>\n"
        f"└─ Исключено: <b>{excluded}</b>\n"
        f"└─ Интервал: <b>{format_interval(interval)}</b>\n"
        f"└─ Режим: {mode_text}",
        reply_markup=broadcast_confirm_keyboard(post_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast:start:"))
async def cb_broadcast_start(callback: CallbackQuery, db_user: User) -> None:
    if _broadcast_service is None:
        await callback.answer("Сервис не инициализирован", show_alert=True)
        return

    post_id = int(callback.data.split(":")[-1])
    active = await store_service.get_active_broadcast(db_user.id)
    if active:
        await callback.answer("Уже идёт рассылка. Остановите её сначала.", show_alert=True)
        return

    try:
        job_id = await _broadcast_service.start_broadcast(post_id, db_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.message.edit_text(
        f"📤 <b>Рассылка #{job_id} запущена</b>\n"
        f"└─ Пост: #{post_id}\n"
        f"└─ Статус: в процессе…",
        reply_markup=broadcast_progress_keyboard(job_id),
        parse_mode="HTML",
    )
    await callback.answer("🚀 Старт!")


@router.callback_query(F.data.startswith("broadcast:stop:"))
async def cb_broadcast_stop(callback: CallbackQuery, db_user: User) -> None:
    if _broadcast_service is None:
        await callback.answer("Сервис не инициализирован", show_alert=True)
        return

    job_id = int(callback.data.split(":")[-1])
    await _broadcast_service.stop_broadcast(job_id, db_user.id)
    await callback.message.edit_text(
        f"⏹ <b>Рассылка #{job_id}</b>\n└─ Остановка…",
        parse_mode="HTML",
    )
    await callback.answer("Остановлено")
