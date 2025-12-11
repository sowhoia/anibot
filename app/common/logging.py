from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from loguru import logger


def setup_logging(level: str = "INFO", log_path: Path | None = None) -> None:
    """
    Единая настройка loguru: консоль + опциональный файл.
    Уровень можно задать через строку уровня (INFO/DEBUG/WARNING/ERROR).
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_path,
            rotation="20 MB",
            retention="14 days",
            level=level.upper(),
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

