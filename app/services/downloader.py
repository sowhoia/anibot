"""
Сервис загрузки видео из Kodik через ffmpeg.

Особенности:
- Загрузка HLS потоков в MP4
- Валидация результата
- Автоматическая очистка временных файлов
- Детальное логирование и обработка ошибок
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import settings
from app.integrations.kodik import KodikClient, KodikError, get_kodik_client


class DownloadErrorType(str, Enum):
    """Типы ошибок загрузки."""

    FFMPEG_NOT_FOUND = "ffmpeg_not_found"
    FFMPEG_FAILED = "ffmpeg_failed"
    FFMPEG_TIMEOUT = "ffmpeg_timeout"
    FILE_NOT_CREATED = "file_not_created"
    FILE_EMPTY = "file_empty"
    FILE_TOO_SMALL = "file_too_small"
    KODIK_ERROR = "kodik_error"
    INVALID_INPUT = "invalid_input"


class DownloadError(Exception):
    """Ошибка загрузки с типизацией."""

    def __init__(
        self,
        message: str,
        error_type: DownloadErrorType,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.error_type.value}] {super().__str__()}"


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Результат успешной загрузки."""

    path: Path
    size_bytes: int
    checksum: str
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """Параметры запроса на загрузку."""

    external_ids: dict[str, Any]
    translation_id: int
    episode_num: int
    quality: int = 720
    anime_id: str | None = None

    def __post_init__(self) -> None:
        if not self.external_ids:
            raise DownloadError(
                "external_ids cannot be empty",
                DownloadErrorType.INVALID_INPUT,
            )
        if self.translation_id <= 0:
            raise DownloadError(
                f"Invalid translation_id: {self.translation_id}",
                DownloadErrorType.INVALID_INPUT,
            )
        if self.episode_num <= 0:
            raise DownloadError(
                f"Invalid episode_num: {self.episode_num}",
                DownloadErrorType.INVALID_INPUT,
            )

    @property
    def source_id(self) -> str:
        """Возвращает идентификатор для имени файла."""
        for key in ("shikimori", "kinopoisk", "imdb"):
            if val := self.external_ids.get(key):
                return str(val)
        return "unknown"

    def to_filename(self) -> str:
        """Генерирует имя файла для загрузки."""
        return f"{self.source_id}-{self.translation_id}-{self.episode_num}.mp4"


class Downloader:
    """
    Сервис загрузки видео из Kodik.

    Использует ffmpeg для загрузки HLS потоков и конвертации в MP4.
    Поддерживает валидацию результата и автоматическую очистку.

    Примеры:
        >>> downloader = Downloader()
        >>> request = DownloadRequest(
        ...     external_ids={"shikimori": "12345"},
        ...     translation_id=610,
        ...     episode_num=1
        ... )
        >>> result = await downloader.download(request)
        >>> print(f"Downloaded: {result.path} ({result.size_bytes} bytes)")
    """

    # Минимальный размер файла в байтах (защита от пустых/битых файлов)
    MIN_FILE_SIZE: int = 1024 * 100  # 100 KB

    # ffmpeg аргументы для оптимальной загрузки
    FFMPEG_ARGS: tuple[str, ...] = (
        "-y",  # перезапись файла
        "-hide_banner",  # скрыть баннер
        "-loglevel", "warning",  # уменьшить вывод
        "-c", "copy",  # копирование без перекодирования
        "-bsf:a", "aac_adtstoasc",  # AAC bitstream filter
        "-movflags", "+faststart",  # оптимизация для progressive download
    )

    def __init__(
        self,
        temp_dir: Path | None = None,
        timeout_seconds: int | None = None,
        kodik_client: KodikClient | None = None,
    ) -> None:
        """
        Args:
            temp_dir: Директория для временных файлов
            timeout_seconds: Таймаут загрузки в секундах
            kodik_client: Клиент Kodik API (опционально)
        """
        self._temp_dir = temp_dir or settings.temp_dir
        self._timeout = timeout_seconds or settings.download_timeout_seconds
        self._kodik = kodik_client or get_kodik_client()
        self._ensure_temp_dir()
        self._check_ffmpeg()

    def _ensure_temp_dir(self) -> None:
        """Создает директорию для временных файлов."""
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Using temp directory: {}", self._temp_dir)

    def _check_ffmpeg(self) -> None:
        """Проверяет наличие ffmpeg в системе."""
        if not shutil.which("ffmpeg"):
            raise DownloadError(
                "ffmpeg not found in PATH. Please install ffmpeg.",
                DownloadErrorType.FFMPEG_NOT_FOUND,
            )

    async def download(self, request: DownloadRequest) -> DownloadResult:
        """
        Загружает эпизод и возвращает результат.

        Args:
            request: Параметры загрузки

        Returns:
            DownloadResult с путем к файлу и метаданными

        Raises:
            DownloadError: При любой ошибке загрузки
        """
        out_path = self._temp_dir / request.to_filename()

        logger.info(
            "Starting download: source={} tr={} ep={} q={}",
            request.source_id,
            request.translation_id,
            request.episode_num,
            request.quality,
        )

        try:
            m3u8_url = await self._get_m3u8(request)
            await self._run_ffmpeg(m3u8_url, out_path)
            return await self._validate_and_get_result(out_path)
        except DownloadError:
            await self.cleanup_file(out_path)
            raise
        except Exception as exc:
            await self.cleanup_file(out_path)
            logger.exception("Unexpected download error")
            raise DownloadError(
                f"Unexpected error: {exc}",
                DownloadErrorType.FFMPEG_FAILED,
                {"original_error": str(exc)},
            ) from exc

    async def _get_m3u8(self, request: DownloadRequest) -> str:
        """Получает URL m3u8 плейлиста."""
        try:
            return await self._kodik.get_episode_m3u8(
                external_ids=request.external_ids,
                translation_id=request.translation_id,
                episode_num=request.episode_num,
                quality=request.quality,
            )
        except KodikError as exc:
            raise DownloadError(
                f"Failed to get m3u8 URL: {exc}",
                DownloadErrorType.KODIK_ERROR,
                {"kodik_error": str(exc)},
            ) from exc

    async def _run_ffmpeg(self, m3u8_url: str, out_path: Path) -> None:
        """Запускает ffmpeg для загрузки."""
        cmd = ["ffmpeg", "-i", m3u8_url, *self.FFMPEG_ARGS, str(out_path)]

        logger.debug("Running ffmpeg: {}", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise DownloadError(
                f"ffmpeg timed out after {self._timeout}s",
                DownloadErrorType.FFMPEG_TIMEOUT,
                {"timeout_seconds": self._timeout},
            )

        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace")
            logger.error("ffmpeg failed: {}", stderr_text[:500])
            raise DownloadError(
                f"ffmpeg exited with code {proc.returncode}",
                DownloadErrorType.FFMPEG_FAILED,
                {"returncode": proc.returncode, "stderr": stderr_text[:1000]},
            )

    async def _validate_and_get_result(self, path: Path) -> DownloadResult:
        """Валидирует загруженный файл и возвращает результат."""
        if not path.exists():
            raise DownloadError(
                "Output file was not created",
                DownloadErrorType.FILE_NOT_CREATED,
            )

        size = path.stat().st_size

        if size == 0:
            raise DownloadError(
                "Output file is empty",
                DownloadErrorType.FILE_EMPTY,
            )

        if size < self.MIN_FILE_SIZE:
            raise DownloadError(
                f"Output file too small: {size} bytes (min: {self.MIN_FILE_SIZE})",
                DownloadErrorType.FILE_TOO_SMALL,
                {"size_bytes": size, "min_size": self.MIN_FILE_SIZE},
            )

        checksum = await self._compute_checksum(path)

        logger.info(
            "Download complete: {} ({} bytes, checksum: {})",
            path.name,
            size,
            checksum[:16],
        )

        return DownloadResult(
            path=path,
            size_bytes=size,
            checksum=checksum,
        )

    @staticmethod
    async def _compute_checksum(path: Path, algorithm: str = "md5") -> str:
        """Вычисляет контрольную сумму файла."""
        loop = asyncio.get_running_loop()

        def _hash():
            h = hashlib.new(algorithm)
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()

        return await loop.run_in_executor(None, _hash)

    async def cleanup_file(self, path: Path) -> bool:
        """
        Безопасно удаляет файл.

        Returns:
            True если файл был удален, False если его не было
        """
        try:
            if path.exists():
                os.remove(path)
                logger.debug("Cleaned up temp file: {}", path)
                return True
            return False
        except OSError as exc:
            logger.warning("Failed to cleanup file {}: {}", path, exc)
            return False

    async def cleanup_all(self) -> int:
        """
        Удаляет все временные файлы.

        Returns:
            Количество удаленных файлов
        """
        count = 0
        for f in self._temp_dir.glob("*.mp4"):
            if await self.cleanup_file(f):
                count += 1
        logger.info("Cleaned up {} temp files", count)
        return count
