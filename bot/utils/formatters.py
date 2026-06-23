from datetime import datetime

from bot.db.models import Log, User


def format_interval(seconds: int) -> str:
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60} мин"
    return f"{seconds} сек"


def format_main_menu(is_super: bool) -> str:
    role = "👑 Супер-админ" if is_super else "💎 Админ"
    return (
        "━━━━━━━━━━━━━━━━━━\n"
        f"  <b>📊 ПАНЕЛЬ РАССЫЛКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"└─ Роль: {role}\n"
        f"└─ Перешлите пост или отправьте медиа\n"
        f"└─ Бот сохранит <b>forward</b> для Premium-эмодзи\n"
    )


def format_admin_dashboard(
    admins_count: int,
    chats_count: int,
    sent_today: int,
    problematic_count: int = 0,
) -> str:
    text = (
        "━━━━━━━━━━━━━━━━━━\n"
        f"  <b>👑 ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"└─ Активных админов: <b>{admins_count}</b>\n"
        f"└─ Подключенных чатов: <b>{chats_count}</b>\n"
        f"└─ Отправлено постов за сегодня: <b>{sent_today}</b>\n"
    )
    if problematic_count:
        text += f"└─ ⚠️ Проблемных чатов: <b>{problematic_count}</b>\n"
    return text


def format_post_view(post_id: int, preview: str, send_mode: str, copy_caption: str | None) -> str:
    if send_mode == "copy":
        mode_line = "✏️ Режим: <b>Copy</b> (Premium-эмодзи не сохраняются)"
        if copy_caption:
            mode_line += f"\n└─ Подпись: {copy_caption[:100]}"
    else:
        mode_line = "🔄 Режим: <b>Forward</b> (Premium-эмодзи сохраняются)"
    return f"📝 <b>Пост #{post_id}</b>\n{mode_line}\n└─ {preview[:200]}"


def format_admin_chats_page(chats: list, page: int, total_pages: int, total: int) -> str:
    lines = [
        "━━━━━━━━━━━━━━━━━━",
        f"  <b>📋 УПРАВЛЕНИЕ ЧАТАМИ ({total})</b>",
        "━━━━━━━━━━━━━━━━━━\n",
        "✅ — активный · ⚠️ — проблемный\n",
    ]
    if not chats:
        lines.append("Список пуст.")
    else:
        for chat in chats:
            icon = "✅" if chat.is_active else "⚠️"
            status = "" if chat.is_active else f" ({chat.status})"
            lines.append(f"{icon} {chat.title}{status}")
    lines.append(f"\nСтраница {page + 1}/{total_pages}")
    return "\n".join(lines)


def format_post_saved(post_id: int, content_type: str, is_album: bool) -> str:
    album = " · альбом" if is_album else ""
    return (
        f"✅ <b>Пост #{post_id}</b> сохранён\n"
        f"└─ Тип: {content_type}{album}\n"
        f"└─ Отправка через <b>forward</b> — Premium-эмодзи сохранятся"
    )


def format_log_entry(log: Log) -> str:
    mark = "❌" if log.is_error else "✅"
    user_name = "—"
    if log.user:
        user_name = log.user.full_name or log.user.username or str(log.user.id)
    chat_name = log.chat.title if log.chat else "—"
    ts = log.created_at.strftime("%d.%m %H:%M") if isinstance(log.created_at, datetime) else "—"
    detail = log.details or log.action
    return f"{mark} <code>{ts}</code> · {user_name} → {chat_name}\n└─ {detail}"


def format_logs_page(logs: list[Log]) -> str:
    if not logs:
        return "📁 Журнал пуст"
    lines = ["<b>📁 Журнал рассылок</b>\n"]
    for log in logs:
        lines.append(format_log_entry(log))
    return "\n\n".join(lines)


def format_admin_line(admin: User) -> str:
    crown = "👑" if admin.is_super_admin else "👤"
    name = admin.full_name or admin.username or str(admin.id)
    return f"{crown} {name} (<code>{admin.id}</code>)"


def format_chats_page(chats: list, page: int, total_pages: int, total: int) -> str:
    lines = [
        "━━━━━━━━━━━━━━━━━━",
        f"  <b>💬 ЧАТЫ ({total})</b>",
        "━━━━━━━━━━━━━━━━━━\n",
    ]
    if not chats:
        lines.append("Чаты не найдены. Добавьте бота админом в канал/чат.")
    else:
        for i, chat in enumerate(chats, start=page * len(chats) + 1):
            icon = "📢" if chat.chat_type == "channel" else "💬"
            lines.append(f"{i}. {icon} {chat.title}")
    lines.append(f"\nСтраница {page + 1}/{total_pages}")
    return "\n".join(lines)
