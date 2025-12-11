from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.services.search import SearchService
from app.bot.keyboards.common import pagination_keyboard

router = Router(name="search")
search_service = SearchService()


@router.message(F.text, F.text.len() >= 2)
async def handle_search(message: Message) -> None:
    query = message.text.strip()
    page = 1
    items, total = await search_service.search(query=query, page=page, limit=5)
    if not items:
        await message.answer("Ничего не найдено 🤷")
        return

    text = format_results(items, total, page)
    kb = build_results_keyboard(items, page, total)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("search:page:"))
async def handle_page(callback: CallbackQuery) -> None:
    _, _, raw_page = callback.data.split(":")
    page = max(1, int(raw_page))
    query = callback.message.text.split("\n", 1)[0] if callback.message else ""
    items, total = await search_service.search(query=query, page=page, limit=5)
    text = format_results(items, total, page)
    kb = build_results_keyboard(items, page, total)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


def build_results_keyboard(items, page: int, total: int) -> InlineKeyboardMarkup:
    # Заглушка: кнопки выбора аниме по id
    item_buttons = [
        [InlineKeyboardButton(text=item.title, callback_data=f"anime:{item.id}")]
        for item in items
    ]
    pag = pagination_keyboard(prefix="search", page=page, has_prev=page > 1, has_next=page * 5 < total)
    if pag.inline_keyboard:
        item_buttons.append(pag.inline_keyboard[0])
    return InlineKeyboardMarkup(inline_keyboard=item_buttons)


def format_results(items, total: int, page: int) -> str:
    lines = [f"Страница {page}, найдено {total}"]
    for idx, item in enumerate(items, start=1 + (page - 1) * 5):
        lines.append(f"{idx}. {item.title} ({item.year or '—'})")
    return "\n".join(lines)

