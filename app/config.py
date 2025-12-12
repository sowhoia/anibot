"""
Конфигурация приложения.

Все настройки загружаются из переменных окружения или .env файла.
Использует Pydantic для валидации и типизации.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import (
    Field,
    PostgresDsn,
    RedisDsn,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация приложения.

    Все значения можно переопределить через переменные окружения.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ================== Telegram Bot ==================
    bot_token: str = Field(
        ...,
        description="Токен Telegram бота от @BotFather",
        min_length=40,
    )

    # ================== Telegram User API ==================
    user_api_session_string: str = Field(
        ...,
        description="Строка сессии Pyrogram для User API",
    )
    user_api_api_id: int = Field(
        ...,
        description="API ID из my.telegram.org",
        gt=0,
    )
    user_api_api_hash: str = Field(
        ...,
        description="API Hash из my.telegram.org",
        min_length=32,
        max_length=32,
    )
    upload_chat_id: str = Field(
        default="me",
        description="ID чата для загрузки видео (число или username)",
    )
    telegram_proxy_url: str | None = Field(
        default=None,
        description="Прокси для Telegram API (http://user:pass@host:port или socks5://host:port)",
    )

    # ================== Database ==================
    postgres_dsn: Annotated[str, PostgresDsn] = Field(
        ...,
        description="PostgreSQL connection string",
        examples=["postgresql+asyncpg://user:pass@localhost:5432/anibot"],
    )
    db_pool_size: int = Field(
        default=5,
        description="Размер пула соединений БД",
        ge=1,
        le=100,
    )
    db_max_overflow: int = Field(
        default=10,
        description="Максимальное превышение пула соединений",
        ge=0,
        le=50,
    )
    db_pool_timeout: int = Field(
        default=30,
        description="Таймаут ожидания соединения из пула (секунды)",
        ge=1,
        le=300,
    )

    # ================== Redis ==================
    redis_url: Annotated[str, RedisDsn] = Field(
        ...,
        description="Redis connection URL",
        examples=["redis://localhost:6379/0"],
    )
    redis_cache_ttl: int = Field(
        default=3600,
        description="TTL кэша Redis в секундах",
        ge=60,
        le=86400,
    )

    # ================== Kodik API ==================
    kodik_token: str | None = Field(
        default=None,
        description="API токен Kodik (опционально)",
    )
    kodik_rps_limit: int = Field(
        default=90,
        description="Лимит запросов к Kodik API в секунду",
        ge=1,
        le=200,
    )

    # ================== Files & Downloads ==================
    temp_dir: Path = Field(
        default=Path("/tmp/anibot"),
        description="Директория для временных файлов",
    )
    download_timeout_seconds: int = Field(
        default=600,
        description="Таймаут загрузки видео в секундах",
        ge=60,
        le=3600,
    )
    max_file_size_mb: int = Field(
        default=4000,
        description="Максимальный размер файла для загрузки (MB) - 4GB для премиум",
        ge=100,
        le=4000,
    )

    # ================== Workers ==================
    upload_poll_interval: int = Field(
        default=5,
        description="Интервал опроса очереди загрузки (секунды)",
        ge=1,
        le=60,
    )
    worker_concurrency: int = Field(
        default=3,
        description="Количество параллельных воркеров",
        ge=1,
        le=10,
    )
    ingest_batch_size: int = Field(
        default=100,
        description="Размер батча для импорта данных",
        ge=10,
        le=1000,
    )

    # ================== Search ==================
    search_results_per_page: int = Field(
        default=5,
        description="Количество результатов поиска на страницу",
        ge=1,
        le=20,
    )
    search_cache_enabled: bool = Field(
        default=True,
        description="Включить кэширование поиска",
    )

    # ================== Logging ==================
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    log_file: Path | None = Field(
        default=None,
        description="Путь к файлу логов (опционально)",
    )
    log_json: bool = Field(
        default=False,
        description="Использовать JSON формат для логов",
    )

    @field_validator("temp_dir", mode="after")
    @classmethod
    def create_temp_dir(cls, v: Path) -> Path:
        """Создает директорию для временных файлов."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """Нормализует уровень логирования."""
        return v.upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def validate_telegram_config(self) -> "Settings":
        """Валидирует конфигурацию Telegram."""
        if self.bot_token and not self.bot_token.count(":") == 1:
            raise ValueError("Invalid bot_token format")
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Возвращает кэшированный экземпляр настроек.

    Используйте эту функцию вместо прямого создания Settings()
    для оптимизации производительности.
    """
    return Settings()


# Singleton для обратной совместимости
settings = get_settings()


# Константы приложения (не настраиваются через env)
class AppConstants:
    """Константы приложения."""

    APP_NAME: str = "AniBot"
    APP_VERSION: str = "1.0.0"

    # Поддерживаемые качества видео
    VIDEO_QUALITIES: tuple[int, ...] = (360, 480, 720, 1080)
    DEFAULT_VIDEO_QUALITY: int = 720

    # Типы контента Kodik
    ANIME_TYPES: tuple[str, ...] = ("anime", "anime-serial")
    SERIAL_TYPES: tuple[str, ...] = (
        "anime-serial",
        "cartoon-serial",
        "documentary-serial",
        "russian-serial",
        "foreign-serial",
    )

    # Приоритет внешних ID
    EXTERNAL_ID_PRIORITY: tuple[str, ...] = ("shikimori", "kinopoisk", "imdb")

    # Telegram лимиты
    TG_MAX_MESSAGE_LENGTH: int = 4096
    TG_MAX_CAPTION_LENGTH: int = 1024
    TG_MAX_FILE_SIZE: int = 4 * 1024 * 1024 * 1024  # 4 GB (Premium)

    # Retry конфигурация
    MAX_RETRIES: int = 3
    RETRY_DELAY_BASE: float = 1.0
    RETRY_DELAY_MAX: float = 30.0
