from aiogram import Dispatcher

from app.bot.routers import search


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(search.router)

