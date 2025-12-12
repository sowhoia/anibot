"""
Роутер для поиска аниме.

Обрабатывает текстовые запросы и пагинацию результатов.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.keyboards.common import pagination_keyboard
from app.config import settings
from app.services.search import SearchResult, get_search_service

router = Router(name="search")


@router.message(F.text, F.text.len() >= 2)
async def handle_search(message: Message) -> None:
    """Обрабатывает поисковый запрос."""
    query = message.text.strip()
    service = get_search_service()

    result = await service.search(
        query=query,
        page=1,
        limit=settings.search_results_per_page,
    )

    if not result.items:
        await message.answer("Ничего не найдено")
        return

    text = format_results(result)
    kb = build_results_keyboard(result)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("search:page:"))
async def handle_page(callback: CallbackQuery) -> None:
    """Обрабатывает переключение страницы."""
    if not callback.message or not callback.data:
        await callback.answer()
        return

    _, _, raw_page = callback.data.split(":")
    page = max(1, int(raw_page))

    # Извлекаем запрос из первой строки сообщения
    query = extract_query_from_message(callback.message.text or "")
    if not query:
        await callback.answer("Не удалось определить запрос")
        return

    service = get_search_service()
    result = await service.search(
        query=query,
        page=page,
        limit=settings.search_results_per_page,
    )

    text = format_results(result)
    kb = build_results_keyboard(result)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


def extract_query_from_message(text: str) -> str:
    """Извлекает поисковый запрос из текста сообщения."""
    # Формат: "Поиск: {query}\n..."
    if text.startswith("Поиск: "):
        first_line = text.split("\n", 1)[0]
        return first_line.replace("Поиск: ", "").strip()
    return ""


def build_results_keyboard(result: SearchResult) -> InlineKeyboardMarkup:
    """Создает клавиатуру с результатами и пагинацией."""
    # Кнопки выбора аниме
    item_buttons = [
        [InlineKeyboardButton(
            text=f"{item.title} ({item.year or '—'})",
            callback_data=f"anime:{item.id}",
        )]
        for item in result.items
    ]

    # Пагинация
    pag = pagination_keyboard(
        prefix="search",
        page=result.page,
        has_prev=result.has_prev,
        has_next=result.has_next,
    )

    if pag.inline_keyboard:
        item_buttons.append(pag.inline_keyboard[0])

    return InlineKeyboardMarkup(inline_keyboard=item_buttons)


def format_results(result: SearchResult) -> str:
    """Форматирует результаты поиска."""
    lines = [
        f"Поиск: {result.query}",
        f"Страница {result.page}/{result.total_pages}, найдено: {result.total}",
        "",
    ]

    start_num = (result.page - 1) * result.limit + 1
    for idx, item in enumerate(result.items, start=start_num):
        year = item.year or "—"
        rating = f" ({item.rating:.1f})" if item.rating else ""
        lines.append(f"{idx}. {item.title} ({year}){rating}")

    return "\n".join(lines)
