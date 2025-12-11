from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = Field(..., env="BOT_TOKEN")
    postgres_dsn: str = Field(..., env="POSTGRES_DSN")
    redis_url: str = Field(..., env="REDIS_URL")
    kodik_token: str | None = Field(default=None, env="KODIK_TOKEN")
    kodik_rps_limit: int = Field(default=90, env="KODIK_RPS_LIMIT")
    temp_dir: Path = Field(default=Path("/tmp/anibot"), env="TEMP_DIR")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[Path] = Field(default=None, env="LOG_FILE")
    download_timeout_seconds: int = Field(default=600, env="DOWNLOAD_TIMEOUT_SECONDS")
    upload_poll_interval: int = Field(default=5, env="UPLOAD_POLL_INTERVAL")
    db_pool_size: int = Field(default=5, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, env="DB_MAX_OVERFLOW")

    # Telegram user API (для загрузки в закрытый канал)
    user_api_session_string: str = Field(..., env="USER_API_SESSION_STRING")
    user_api_api_id: int = Field(..., env="USER_API_API_ID")
    user_api_api_hash: str = Field(..., env="USER_API_API_HASH")

    class Config:
        env_file = ".env"


settings = Settings()

