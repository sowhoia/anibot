import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from loguru import logger

from app.config import settings
from app.common.logging import setup_logging
from app.bot.routers import setup_routers


def create_bot_session() -> AiohttpSession:
    """
    Создает сессию для бота с поддержкой прокси.
    
    Если TELEGRAM_PROXY_URL указан в .env, использует его для подключения.
    Формат: socks5://user:pass@host:port или http://user:pass@host:port
    """
    proxy_url = getattr(settings, 'telegram_proxy_url', None)
    
    if proxy_url:
        # aiogram 3.x поддерживает proxy напрямую в AiohttpSession
        logger.info("Using proxy for Telegram API: {}@***", proxy_url.split('@')[0] if '@' in proxy_url else proxy_url)
        return AiohttpSession(proxy=proxy_url)
    
    return AiohttpSession()


async def main() -> None:
    setup_logging(level=settings.log_level, log_path=settings.log_file)
    
    session = create_bot_session()
    
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()
    setup_routers(dp)

    try:
        await dp.start_polling(bot)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())

