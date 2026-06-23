from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import SendMode
from bot.utils.formatters import format_interval
from bot.utils.pagination import build_page_buttons


def close_button(callback_data: str = "menu:close") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="❌ Закрыть", callback_data=callback_data)


def back_button(callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)


def main_menu_keyboard(*, is_super_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📤 Новый пост", callback_data="post:new"),
            InlineKeyboardButton(text="📁 Мои посты", callback_data="post:list:0"),
        ],
        [
            InlineKeyboardButton(text="💬 Чаты", callback_data="chat:list:0"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings:main"),
        ],
    ]
    if is_super_admin:
        rows.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin:dashboard")])
    rows.append([close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_menu_keyboard(post_id: int, send_mode: str = SendMode.FORWARD.value) -> InlineKeyboardMarkup:
    if send_mode == SendMode.COPY.value:
        mode_btn = InlineKeyboardButton(
            text="✏️ Режим: Новый пост (Copy)",
            callback_data=f"post:toggle_mode:{post_id}",
        )
    else:
        mode_btn = InlineKeyboardButton(
            text="🔄 Режим: Пересылка (Forward)",
            callback_data=f"post:toggle_mode:{post_id}",
        )

    rows: list[list[InlineKeyboardButton]] = [[mode_btn]]

    if send_mode == SendMode.COPY.value:
        rows.append([
            InlineKeyboardButton(text="📝 Задать подпись (Copy)", callback_data=f"post:copy_caption:{post_id}")
        ])

    rows.extend([
        [
            InlineKeyboardButton(text="✍️ Редактировать", callback_data=f"post:edit:{post_id}"),
            InlineKeyboardButton(text="🚀 Размножить", callback_data=f"broadcast:confirm:{post_id}"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"post:settings:{post_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post:delete:{post_id}"),
        ],
        [back_button("post:list:0"), close_button()],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_settings_keyboard(post_id: int, interval: int | None, default_interval: int) -> InlineKeyboardMarkup:
    current = interval or default_interval
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⏱ Интервал: {format_interval(current)}", callback_data=f"post:interval:{post_id}")],
            [InlineKeyboardButton(text="🚫 Исключения чатов", callback_data=f"post:exclude:{post_id}:0")],
            [back_button(f"post:view:{post_id}"), close_button()],
        ]
    )


def interval_keyboard(post_id: int) -> InlineKeyboardMarkup:
    intervals = [6000, 7200, 10800, 12000]  # 100, 120, 180, 200 мин
    rows = []
    row: list[InlineKeyboardButton] = []
    for sec in intervals:
        label = format_interval(sec)
        row.append(InlineKeyboardButton(text=label, callback_data=f"post:set_interval:{post_id}:{sec}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="♻️ По умолчанию", callback_data=f"post:set_interval:{post_id}:0")])
    rows.append([back_button(f"post:settings:{post_id}"), close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def exclusion_keyboard(
    post_id: int,
    chats: list,
    excluded_ids: set[int],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    for chat in chats:
        mark = "✅" if chat.id not in excluded_ids else "🚫"
        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {chat.title[:40]}",
                callback_data=f"post:toggle_exclude:{post_id}:{chat.id}:{page}",
            )
        ])
    rows.append(build_page_buttons(f"post:exclude:{post_id}", page, total_pages))
    rows.append([back_button(f"post:settings:{post_id}"), close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_confirm_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Подтвердить рассылку", callback_data=f"broadcast:start:{post_id}")],
            [InlineKeyboardButton(text="🚫 Исключения", callback_data=f"post:exclude:{post_id}:0")],
            [back_button(f"post:view:{post_id}"), close_button()],
        ]
    )


def broadcast_progress_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏹ Остановить рассылку", callback_data=f"broadcast:stop:{job_id}")],
            [close_button()],
        ]
    )


def posts_list_keyboard(posts: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for post in posts:
        preview = (post.caption or post.content_type)[:30]
        rows.append([
            InlineKeyboardButton(text=f"#{post.id} · {preview}", callback_data=f"post:view:{post.id}")
        ])
    rows.append(build_page_buttons("post:list", page, total_pages))
    rows.append([back_button("menu:main"), close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chats_list_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            build_page_buttons("chat:list", page, total_pages),
            [InlineKeyboardButton(text="🔄 Обновить список", callback_data=f"chat:refresh:{page}")],
            [back_button("menu:main"), close_button()],
        ]
    )


def admin_dashboard_keyboard(*, has_problematic: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_problematic:
        rows.append([
            InlineKeyboardButton(text="🗑 Удалить проблемные", callback_data="admin:delete_problematic")
        ])
    rows.extend([
        [
            InlineKeyboardButton(text="📈 Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:add"),
        ],
        [
            InlineKeyboardButton(text="👤 Список админов", callback_data="admin:list:0"),
            InlineKeyboardButton(text="📋 Управление чатами", callback_data="admin:chats:0"),
        ],
        [
            InlineKeyboardButton(text="🚫 Черный список", callback_data="admin:blacklist:0"),
            InlineKeyboardButton(text="📁 Журнал рассылок", callback_data="admin:logs:0"),
        ],
        [back_button("menu:main"), close_button()],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_chats_manage_keyboard(chats: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats:
        icon = "✅" if chat.is_active else "⚠️"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {chat.title[:35]}",
                callback_data=f"admin:chat_info:{chat.id}:{page}",
            ),
            InlineKeyboardButton(
                text="❌ Удалить",
                callback_data=f"admin:chat_delete:{chat.id}:{page}",
            ),
        ])
    rows.append(build_page_buttons("admin:chats", page, total_pages))
    rows.append([back_button("admin:dashboard"), close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def problematic_chats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить проблемные чаты из списка", callback_data="admin:delete_problematic")],
            [close_button()],
        ]
    )


def admins_list_keyboard(admins: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for admin in admins:
        crown = "👑 " if admin.is_super_admin else "👤 "
        name = admin.full_name or admin.username or str(admin.id)
        rows.append([
            InlineKeyboardButton(
                text=f"{crown}{name}",
                callback_data=f"admin:view:{admin.id}",
            )
        ])
    rows.append(build_page_buttons("admin:list", page, total_pages))
    rows.append([back_button("admin:dashboard"), close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_view_keyboard(admin_id: int, is_super: bool) -> InlineKeyboardMarkup:
    rows = []
    if not is_super:
        rows.append([InlineKeyboardButton(text="🗑 Удалить админа", callback_data=f"admin:remove:{admin_id}")])
    rows.append([back_button("admin:list:0"), close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def logs_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            build_page_buttons("admin:logs", page, total_pages),
            [back_button("admin:dashboard"), close_button()],
        ]
    )


def settings_keyboard(default_interval: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⏱ Интервал по умолчанию: {format_interval(default_interval)}", callback_data="settings:interval")],
            [back_button("menu:main"), close_button()],
        ]
    )
