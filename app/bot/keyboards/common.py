from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def pagination_keyboard(
    prefix: str, page: int, has_prev: bool, has_next: bool
) -> InlineKeyboardMarkup:
    buttons = []
    if has_prev:
        buttons.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:page:{page-1}")
        )
    if has_next:
        buttons.append(
            InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:page:{page+1}")
        )
    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])

