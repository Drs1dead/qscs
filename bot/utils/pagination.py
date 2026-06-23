from aiogram.types import InlineKeyboardButton


def paginate(total: int, page: int, per_page: int) -> tuple[int, int, int]:
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    offset = page * per_page
    return page, total_pages, offset


def build_page_buttons(prefix: str, page: int, total_pages: int) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀", callback_data=f"{prefix}:{page - 1}"))
    buttons.append(InlineKeyboardButton(text=f"· {page + 1}/{total_pages} ·", callback_data="noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="▶", callback_data=f"{prefix}:{page + 1}"))
    return buttons
