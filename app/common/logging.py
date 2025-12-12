"""
Конфигурация логирования.

Особенности:
- Structured logging с контекстом
- JSON формат для production
- Ротация файлов
- Интеграция с asyncio
"""

from __future__ import annotations

import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from loguru import logger

# Контекстные переменные для structured logging
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)


def _patcher(record: dict[str, Any]) -> None:
    """Добавляет контекстные переменные в record."""
    record["extra"]["request_id"] = request_id_var.get()
    record["extra"]["user_id"] = user_id_var.get()


# Форматы логов
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "{extra[request_id]} | "
    "<level>{message}</level>"
)

CONSOLE_FORMAT_SIMPLE = (
    "<green>{time:HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<level>{message}</level>"
)

FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "req_id={extra[request_id]} user={extra[user_id]} | "
    "{message}"
)

JSON_FORMAT = "{message}"  # Для JSON используем serialize=True


def setup_logging(
    level: str = "INFO",
    log_path: Path | None = None,
    json_format: bool = False,
    simple_format: bool = False,
) -> None:
    """
    Настраивает логирование приложения.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_path: Путь к файлу логов (опционально)
        json_format: Использовать JSON формат
        simple_format: Использовать упрощенный формат для консоли
    """
    # Удаляем все существующие handlers
    logger.remove()

    # Добавляем patcher для контекстных переменных
    logger.configure(patcher=_patcher)

    # Выбираем формат для консоли
    console_format = CONSOLE_FORMAT_SIMPLE if simple_format else CONSOLE_FORMAT

    # Консольный вывод
    if json_format:
        logger.add(
            sys.stderr,
            level=level.upper(),
            serialize=True,
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stderr,
            level=level.upper(),
            format=console_format,
            colorize=True,
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    # Файловый вывод
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if json_format:
            logger.add(
                log_path,
                level=level.upper(),
                serialize=True,
                rotation="50 MB",
                retention="30 days",
                compression="gz",
                enqueue=True,
                backtrace=True,
                diagnose=True,
            )
        else:
            logger.add(
                log_path,
                level=level.upper(),
                format=FILE_FORMAT,
                rotation="50 MB",
                retention="30 days",
                compression="gz",
                enqueue=True,
                backtrace=True,
                diagnose=True,
            )

    logger.info(
        "Logging configured (level={}, file={}, json={})",
        level,
        log_path or "none",
        json_format,
    )


class LogContext:
    """
    Контекстный менеджер для добавления данных в логи.

    Примеры:
        >>> async with LogContext(request_id="abc123", user_id=42):
        ...     logger.info("Processing request")
    """

    def __init__(
        self,
        request_id: str | None = None,
        user_id: int | None = None,
    ) -> None:
        self._request_id = request_id
        self._user_id = user_id
        self._request_id_token = None
        self._user_id_token = None

    def __enter__(self) -> "LogContext":
        if self._request_id is not None:
            self._request_id_token = request_id_var.set(self._request_id)
        if self._user_id is not None:
            self._user_id_token = user_id_var.set(self._user_id)
        return self

    def __exit__(self, *args) -> None:
        if self._request_id_token is not None:
            request_id_var.reset(self._request_id_token)
        if self._user_id_token is not None:
            user_id_var.reset(self._user_id_token)

    async def __aenter__(self) -> "LogContext":
        return self.__enter__()

    async def __aexit__(self, *args) -> None:
        self.__exit__(*args)


def log_exception(exc: Exception, context: str = "") -> None:
    """
    Логирует исключение с полным traceback.

    Args:
        exc: Исключение
        context: Дополнительный контекст
    """
    logger.opt(exception=exc).error(
        "Exception occurred{}: {}",
        f" in {context}" if context else "",
        str(exc),
    )


def get_logger(name: str) -> "logger":
    """
    Возвращает logger с указанным именем.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        Настроенный logger
    """
    return logger.bind(name=name)
