import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import get_settings
from bot.db.models import SendMode, User
from bot.db.repositories import LogRepository, PostRepository
from bot.db.session import async_session_factory
from bot.keyboards.inline import (
    interval_keyboard,
    post_menu_keyboard,
    settings_keyboard,
)
from bot.services.album_collector import album_collector
from bot.services.post_service import save_post_from_messages
from bot.states.fsm import PostStates
from bot.utils.formatters import format_interval, format_post_saved, format_post_view
from bot.utils.pagination import paginate

router = Router(name="posts")
logger = logging.getLogger(__name__)
settings = get_settings()
_private = F.chat.type == "private"


@router.callback_query(F.data == "post:new")
async def cb_new_post(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostStates.waiting_post)
    await callback.message.edit_text(
        "📤 <b>Новый пост</b>\n\n"
        "Перешлите сообщение из канала или отправьте медиа/текст.\n"
        "Для Premium-эмодзи используйте <b>пересылку (forward)</b>.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(PostStates.waiting_post, _private, F.media_group_id)
async def receive_album_waiting(message: Message, db_user: User, state: FSMContext) -> None:
    messages = await album_collector.collect(message)
    if not messages:
        return
    status = await message.answer("⏳ Собираю альбом…")
    post_id = await save_post_from_messages(db_user.id, messages)
    await state.clear()
    await status.edit_text(
        format_post_saved(post_id, messages[0].content_type, is_album=True),
        reply_markup=post_menu_keyboard(post_id),
        parse_mode="HTML",
    )


@router.message(_private, F.media_group_id)
async def receive_album_anytime(message: Message, db_user: User) -> None:
    messages = await album_collector.collect(message)
    if not messages:
        return
    status = await message.answer("⏳ Собираю альбом…")
    post_id = await save_post_from_messages(db_user.id, messages)
    await status.edit_text(
        format_post_saved(post_id, messages[0].content_type, is_album=True),
        reply_markup=post_menu_keyboard(post_id),
        parse_mode="HTML",
    )


@router.message(PostStates.waiting_post, _private)
async def receive_post(message: Message, db_user: User, state: FSMContext) -> None:
    if not _is_valid_post(message):
        await message.answer("⚠️ Отправьте текст, медиа или перешлите пост.")
        return
    post_id = await save_post_from_messages(db_user.id, [message])
    await state.clear()
    await message.answer(
        format_post_saved(post_id, message.content_type, is_album=False),
        reply_markup=post_menu_keyboard(post_id),
        parse_mode="HTML",
    )


@router.message(_private, F.forward_from_chat | F.forward_origin | F.text | F.photo | F.video | F.audio | F.document | F.animation)
async def receive_post_anytime(message: Message, db_user: User, state: FSMContext) -> None:
    if message.media_group_id:
        return
    current = await state.get_state()
    if current == PostStates.waiting_post.state:
        return
    if not _is_valid_post(message):
        return
    post_id = await save_post_from_messages(db_user.id, [message])
    await message.answer(
        format_post_saved(post_id, message.content_type, is_album=False),
        reply_markup=post_menu_keyboard(post_id),
        parse_mode="HTML",
    )


def _is_valid_post(message: Message) -> bool:
    return bool(
        message.forward_from_chat
        or message.forward_origin
        or message.text
        or message.photo
        or message.video
        or message.audio
        or message.document
        or message.animation
    )


@router.callback_query(F.data.startswith("post:list:"))
async def cb_posts_list(callback: CallbackQuery, db_user: User) -> None:
    page = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = PostRepository(session)
        total = await repo.count_by_owner(db_user.id)
        page, total_pages, offset = paginate(total, page, settings.posts_per_page)
        posts = await repo.list_by_owner(db_user.id, offset=offset, limit=settings.posts_per_page)

    from bot.keyboards.inline import posts_list_keyboard

    await callback.message.edit_text(
        f"📁 <b>Мои посты</b> ({total})",
        reply_markup=posts_list_keyboard(posts, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("post:view:"))
async def cb_post_view(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.get(post_id)
    if post is None:
        await callback.answer("Пост не найден", show_alert=True)
        return
    preview = post.caption or post.content_type
    await callback.message.edit_text(
        format_post_view(post_id, preview, post.send_mode, post.copy_caption),
        reply_markup=post_menu_keyboard(post_id, post.send_mode),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("post:toggle_mode:"))
async def cb_toggle_mode(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.get(post_id)
        if post is None:
            await callback.answer("Пост не найден", show_alert=True)
            return
        new_mode = SendMode.COPY.value if post.send_mode == SendMode.FORWARD.value else SendMode.FORWARD.value
        await repo.set_send_mode(post_id, new_mode)
        post = await repo.get(post_id)

    if new_mode == SendMode.COPY.value:
        await callback.answer(
            "⚠️ При копировании Premium-эмодзи и forward-метки не сохраняются!",
            show_alert=True,
        )
    else:
        await callback.answer("Режим: Forward")

    preview = post.caption or post.content_type if post else ""
    await callback.message.edit_text(
        format_post_view(post_id, preview, new_mode, post.copy_caption if post else None),
        reply_markup=post_menu_keyboard(post_id, new_mode),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("post:copy_caption:"))
async def cb_copy_caption(callback: CallbackQuery, state: FSMContext) -> None:
    post_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.get(post_id)
    if post is None:
        await callback.answer("Пост не найден", show_alert=True)
        return
    if post.send_mode != SendMode.COPY.value:
        await callback.answer("Сначала включите режим Copy", show_alert=True)
        return

    await state.set_state(PostStates.waiting_copy_caption)
    await state.update_data(copy_post_id=post_id)
    await callback.message.edit_text(
        f"📝 <b>Подпись для Copy-режима</b> (пост #{post_id})\n\n"
        "Отправьте текст подписи (HTML).\n"
        "Будет прикреплена к первому медиа или отправлена как текст.\n\n"
        "⚠️ Premium-эмодзи при Copy не сохраняются.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(PostStates.waiting_copy_caption, F.text)
async def save_copy_caption(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    post_id = data.get("copy_post_id")
    if not post_id:
        await state.clear()
        return

    async with async_session_factory() as session:
        repo = PostRepository(session)
        await repo.set_copy_caption(post_id, message.text)
        post = await repo.get(post_id)

    await state.clear()
    preview = post.caption or post.content_type if post else message.text
    await message.answer(
        f"✅ Подпись сохранена для поста #{post_id}",
        reply_markup=post_menu_keyboard(post_id, SendMode.COPY.value),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("post:settings:"))
async def cb_post_settings(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.get(post_id)
    if post is None:
        await callback.answer("Пост не найден", show_alert=True)
        return
    from bot.keyboards.inline import post_settings_keyboard

    await callback.message.edit_text(
        f"⚙️ <b>Настройки поста #{post_id}</b>",
        reply_markup=post_settings_keyboard(post_id, post.interval_seconds, settings.default_interval),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("post:interval:"))
async def cb_post_interval(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[-1])
    await callback.message.edit_text(
        "⏱ <b>Выберите интервал между чатами:</b>",
        reply_markup=interval_keyboard(post_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("post:set_interval:"))
async def cb_set_interval(callback: CallbackQuery) -> None:
    _, _, post_id_str, sec_str = callback.data.split(":")
    post_id = int(post_id_str)
    sec = int(sec_str)
    interval = None if sec == 0 else sec

    if post_id == 0:
        from bot.services.store_service import store_service

        if interval:
            await store_service.set_default_interval(interval)
        await callback.message.edit_text(
            f"⚙️ <b>Глобальные настройки</b>\n✅ Интервал по умолчанию: {format_interval(interval or settings.default_interval)}",
            reply_markup=settings_keyboard(interval or settings.default_interval),
            parse_mode="HTML",
        )
        await callback.answer("Сохранено")
        return

    async with async_session_factory() as session:
        repo = PostRepository(session)
        await repo.set_interval(post_id, interval)
        post = await repo.get(post_id)

    from bot.keyboards.inline import post_settings_keyboard

    await callback.message.edit_text(
        f"⚙️ <b>Настройки поста #{post_id}</b>\n✅ Интервал обновлён",
        reply_markup=post_settings_keyboard(post_id, post.interval_seconds if post else interval, settings.default_interval),
        parse_mode="HTML",
    )
    await callback.answer("Сохранено")


@router.callback_query(F.data.startswith("post:exclude:"))
async def cb_post_exclude(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    post_id = int(parts[2])
    page = int(parts[3])
    async with async_session_factory() as session:
        from bot.db.repositories import ChatRepository, ExclusionRepository

        chat_repo = ChatRepository(session)
        excl_repo = ExclusionRepository(session)
        total = await chat_repo.count_active()
        page, total_pages, offset = paginate(total, page, settings.chats_per_page)
        chats = await chat_repo.list_active(offset=offset, limit=settings.chats_per_page)
        excluded = await excl_repo.get_excluded_ids(post_id)

    from bot.keyboards.inline import exclusion_keyboard

    await callback.message.edit_text(
        f"🚫 <b>Исключения для поста #{post_id}</b>\n"
        f"✅ — отправить · 🚫 — исключить",
        reply_markup=exclusion_keyboard(post_id, chats, excluded, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("post:toggle_exclude:"))
async def cb_toggle_exclude(callback: CallbackQuery) -> None:
    _, _, post_id_str, chat_id_str, page_str = callback.data.split(":")
    post_id = int(post_id_str)
    chat_id = int(chat_id_str)
    page = int(page_str)
    async with async_session_factory() as session:
        from bot.db.repositories import ChatRepository, ExclusionRepository

        excl_repo = ExclusionRepository(session)
        await excl_repo.toggle(post_id, chat_id)
        chat_repo = ChatRepository(session)
        total = await chat_repo.count_active()
        page, total_pages, offset = paginate(total, page, settings.chats_per_page)
        chats = await chat_repo.list_active(offset=offset, limit=settings.chats_per_page)
        excluded = await excl_repo.get_excluded_ids(post_id)

    from bot.keyboards.inline import exclusion_keyboard

    await callback.message.edit_reply_markup(
        reply_markup=exclusion_keyboard(post_id, chats, excluded, page, total_pages)
    )
    await callback.answer("Обновлено")


@router.callback_query(F.data.startswith("post:delete:"))
async def cb_delete_post(callback: CallbackQuery, db_user: User) -> None:
    post_id = int(callback.data.split(":")[-1])
    async with async_session_factory() as session:
        repo = PostRepository(session)
        log_repo = LogRepository(session)
        post = await repo.get(post_id)
        if post and post.owner_id == db_user.id:
            await repo.delete(post_id)
            await log_repo.add(user_id=db_user.id, post_id=post_id, action="post_deleted")
    await callback.message.edit_text("🗑 Пост удалён")
    await callback.answer()


@router.callback_query(F.data.startswith("post:edit:"))
async def cb_edit_post(callback: CallbackQuery, state: FSMContext) -> None:
    post_id = int(callback.data.split(":")[-1])
    await state.set_state(PostStates.editing_caption)
    await state.update_data(edit_post_id=post_id)
    await callback.message.edit_text(
        f"✍️ Отправьте новый caption для поста #{post_id}\n"
        f"<i>Forward-сообщения отправляются как есть; caption хранится для справки.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(PostStates.editing_caption, F.text)
async def save_edited_caption(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    post_id = data.get("edit_post_id")
    if not post_id:
        await state.clear()
        return
    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.get(post_id)
        if post:
            post.caption = message.text
            await session.commit()
    await state.clear()
    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.get(post_id)
    send_mode = post.send_mode if post else SendMode.FORWARD.value
    await message.answer(
        f"✅ Caption обновлён для поста #{post_id}",
        reply_markup=post_menu_keyboard(post_id, send_mode),
    )
