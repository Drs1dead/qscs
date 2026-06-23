from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import get_settings
from bot.db.models import Chat
from bot.db.repositories import ChatRepository, LogRepository, UserRepository
from bot.db.session import async_session_factory
from bot.keyboards.inline import (
    admin_chats_manage_keyboard,
    admin_dashboard_keyboard,
    admin_view_keyboard,
    admins_list_keyboard,
    logs_keyboard,
)
from bot.states.fsm import AdminStates
from bot.utils.formatters import (
    format_admin_chats_page,
    format_admin_dashboard,
    format_admin_line,
    format_logs_page,
)
from bot.utils.pagination import paginate

router = Router(name="admin")
settings = get_settings()


async def _load_dashboard() -> tuple[str, object]:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        log_repo = LogRepository(session)
        admins_count = await user_repo.count_admins()
        chats_count = await chat_repo.count_active()
        sent_today = await log_repo.count_today_sent()
        problematic = await chat_repo.count_inactive()

    text = format_admin_dashboard(admins_count, chats_count, sent_today, problematic)
    kb = admin_dashboard_keyboard(has_problematic=problematic > 0)
    return text, kb


@router.callback_query(F.data == "admin:dashboard")
async def cb_admin_dashboard(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    text, kb = await _load_dashboard()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        log_repo = LogRepository(session)
        admins = await user_repo.count_admins()
        chats = await chat_repo.count_active()
        logs_total = await log_repo.count_all()
        sent_today = await log_repo.count_today_sent()
        problematic = await chat_repo.count_inactive()

    _, kb = await _load_dashboard()
    await callback.message.edit_text(
        f"📈 <b>Статистика</b>\n\n"
        f"└─ Админов: <b>{admins}</b>\n"
        f"└─ Активных чатов: <b>{chats}</b>\n"
        f"└─ Проблемных чатов: <b>{problematic}</b>\n"
        f"└─ Логов всего: <b>{logs_total}</b>\n"
        f"└─ Отправок сегодня: <b>{sent_today}</b>",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:add")
async def cb_admin_add(callback: CallbackQuery, state: FSMContext, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_admin_id)
    await callback.message.edit_text(
        "➕ <b>Добавить админа</b>\n\n"
        "Отправьте Telegram ID или перешлите сообщение от пользователя.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_admin_id)
async def receive_admin_id(message: Message, state: FSMContext) -> None:
    user_id: int | None = None
    username = None
    full_name = None

    if message.forward_from:
        user_id = message.forward_from.id
        username = message.forward_from.username
        full_name = message.forward_from.full_name
    elif message.text and message.text.strip().isdigit():
        user_id = int(message.text.strip())

    if user_id is None:
        await message.answer("⚠️ Укажите числовой ID или перешлите сообщение.")
        return

    async with async_session_factory() as session:
        repo = UserRepository(session)
        log_repo = LogRepository(session)
        await repo.upsert(user_id, username=username, full_name=full_name)
        await log_repo.add(user_id=message.from_user.id, action="admin_added", details=str(user_id))

    await state.clear()
    text, kb = await _load_dashboard()
    await message.answer(
        f"✅ Админ <code>{user_id}</code> добавлен",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:list:"))
async def cb_admin_list(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    page = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = UserRepository(session)
        total = await repo.count_admins()
        page, total_pages, offset = paginate(total, page, settings.admins_per_page)
        admins = await repo.list_admins(offset=offset, limit=settings.admins_per_page)

    lines = "\n".join(format_admin_line(a) for a in admins) or "Список пуст"
    await callback.message.edit_text(
        f"👤 <b>Админы</b>\n\n{lines}",
        reply_markup=admins_list_keyboard(admins, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:view:"))
async def cb_admin_view(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    admin_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = UserRepository(session)
        admin = await repo.get(admin_id)

    if admin is None:
        await callback.answer("Не найден", show_alert=True)
        return

    await callback.message.edit_text(
        f"👤 <b>Админ</b>\n{format_admin_line(admin)}",
        reply_markup=admin_view_keyboard(admin_id, admin.is_super_admin),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:remove:"))
async def cb_admin_remove(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    admin_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = UserRepository(session)
        log_repo = LogRepository(session)
        admin = await repo.get(admin_id)
        if admin and not admin.is_super_admin:
            await repo.deactivate(admin_id)
            await log_repo.add(
                user_id=callback.from_user.id,
                action="admin_removed",
                details=str(admin_id),
            )

    text, kb = await _load_dashboard()
    await callback.message.edit_text("🗑 Админ деактивирован", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:logs:"))
async def cb_admin_logs(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    page = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        log_repo = LogRepository(session)
        total = await log_repo.count_all()
        page, total_pages, offset = paginate(total, page, settings.logs_per_page)
        logs = await log_repo.recent(offset=offset, limit=settings.logs_per_page)

    await callback.message.edit_text(
        format_logs_page(logs),
        reply_markup=logs_keyboard(page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:blacklist:"))
async def cb_blacklist(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    async with async_session_factory() as session:
        chat_repo = ChatRepository(session)
        chats = await chat_repo.list_inactive()

    if not chats:
        text = "🚫 <b>Чёрный список</b>\n\nПуст"
    else:
        lines = "\n".join(f"· {c.title} (<code>{c.id}</code>) — {c.status}" for c in chats)
        text = f"🚫 <b>Чёрный список</b>\n\n{lines}"

    _, kb = await _load_dashboard()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:delete_problematic")
async def cb_delete_problematic(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    deleted = 0
    async with async_session_factory() as session:
        chat_repo = ChatRepository(session)
        log_repo = LogRepository(session)
        deleted = await chat_repo.delete_all_inactive()
        if deleted:
            await log_repo.add(
                user_id=callback.from_user.id,
                action="chats_deleted_inactive",
                details=f"Удалено: {deleted}",
            )

    text, kb = await _load_dashboard()
    await callback.message.edit_text(
        f"🗑 Удалено проблемных чатов: <b>{deleted}</b>\n\n{text}",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin:chats:"))
async def cb_admin_chats(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    page = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        chat_repo = ChatRepository(session)
        total = await chat_repo.count_all()
        page, total_pages, offset = paginate(total, page, settings.chats_per_page)
        chats = await chat_repo.list_all(offset=offset, limit=settings.chats_per_page)

    await callback.message.edit_text(
        format_admin_chats_page(chats, page, total_pages, total),
        reply_markup=admin_chats_manage_keyboard(chats, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:chat_info:"))
async def cb_chat_info(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    parts = callback.data.split(":")
    chat_id = int(parts[2])
    async with async_session_factory() as session:
        chat = await session.get(Chat, chat_id)
    if chat is None:
        await callback.answer("Чат не найден", show_alert=True)
        return

    status = "активен" if chat.is_active else f"проблемный ({chat.status})"
    await callback.answer(f"{chat.title} — {status}", show_alert=True)


@router.callback_query(F.data.startswith("admin:chat_delete:"))
async def cb_chat_delete(callback: CallbackQuery, is_super_admin: bool) -> None:
    if not is_super_admin:
        await callback.answer("👑 Только для супер-админа", show_alert=True)
        return

    parts = callback.data.split(":")
    chat_id = int(parts[2])
    page = int(parts[3])

    async with async_session_factory() as session:
        chat_repo = ChatRepository(session)
        log_repo = LogRepository(session)
        chat = await session.get(Chat, chat_id)
        title = chat.title if chat else str(chat_id)
        await chat_repo.delete_permanently(chat_id)
        await log_repo.add(
            user_id=callback.from_user.id,
            action="chat_deleted",
            details=f"{title} ({chat_id})",
        )
        total = await chat_repo.count_all()
        page, total_pages, offset = paginate(total, page, settings.chats_per_page)
        chats = await chat_repo.list_all(offset=offset, limit=settings.chats_per_page)

    await callback.message.edit_text(
        format_admin_chats_page(chats, page, total_pages, total),
        reply_markup=admin_chats_manage_keyboard(chats, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer(f"🗑 {title} удалён")
