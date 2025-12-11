import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import settings
from app.common.logging import setup_logging
from app.db.session import get_session
from app.db import repo
from app.bot.routers import setup_routers


async def main() -> None:
    setup_logging(level=settings.log_level, log_path=settings.log_file)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    setup_routers(dp)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

