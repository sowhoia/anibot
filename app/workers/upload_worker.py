"""
Worker для загрузки видео в Telegram.

Особенности:
- Graceful shutdown
- Retry при ошибках
- Мониторинг состояния
- Конфигурируемый интервал опроса
"""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger

from app.common.async_utils import retry_async
from app.common.logging import setup_logging
from app.config import settings
from app.db import repo
from app.db.session import get_session
from app.integrations.telegram_uploader import (
    EpisodeUploadTask,
    OrderedUploadQueue,
    build_pyrogram_client,
    shutdown_uploader,
)
from app.services.downloader import Downloader, DownloadError, DownloadResult


@dataclass
class WorkerStats:
    """Статистика worker."""

    started_at: datetime
    processed_count: int = 0
    failed_count: int = 0
    last_poll_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "uptime_seconds": (datetime.utcnow() - self.started_at).total_seconds(),
        }


class UploadWorker:
    """
    Worker для загрузки эпизодов в Telegram.

    Периодически проверяет БД на наличие эпизодов без медиа,
    скачивает их и загружает в Telegram.
    """

    def __init__(
        self,
        poll_interval: int | None = None,
        batch_size: int = 10,
        max_retries: int = 3,
    ) -> None:
        """
        Args:
            poll_interval: Интервал опроса БД (секунды)
            batch_size: Количество эпизодов за один опрос
            max_retries: Максимальное количество retry для загрузки
        """
        self._poll_interval = poll_interval or settings.upload_poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries

        self._session_factory = get_session()
        self._downloader = Downloader()
        self._client = None
        self._queue: OrderedUploadQueue | None = None

        self._shutdown_event = asyncio.Event()
        self._stats = WorkerStats(started_at=datetime.utcnow())

    async def start(self) -> None:
        """Запускает worker."""
        logger.info("Starting upload worker...")

        # Инициализируем Telegram клиент
        self._client = build_pyrogram_client()
        await self._client.start()

        # Создаем очередь загрузки
        self._queue = OrderedUploadQueue(self._client)

        # Настраиваем обработчики сигналов
        self._setup_signal_handlers()

        logger.info(
            "Upload worker started (poll_interval={}s, batch_size={})",
            self._poll_interval,
            self._batch_size,
        )

        await self._run_loop()

    async def stop(self) -> None:
        """Останавливает worker."""
        logger.info("Stopping upload worker...")
        self._shutdown_event.set()

        if self._queue:
            await self._queue.shutdown()

        if self._client:
            await self._client.stop()

        logger.info(
            "Upload worker stopped. Stats: {}",
            self._stats.to_dict(),
        )

    def _setup_signal_handlers(self) -> None:
        """Настраивает обработчики сигналов для graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_signal(sig)),
            )

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Обрабатывает сигнал остановки."""
        logger.info("Received signal {}, initiating shutdown...", sig.name)
        await self.stop()

    async def _run_loop(self) -> None:
        """Основной цикл worker."""
        while not self._shutdown_event.is_set():
            try:
                await self._poll_and_process()
            except Exception as exc:
                logger.exception("Error in poll loop: {}", exc)

            # Ждем следующего опроса или shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._poll_interval,
                )
            except asyncio.TimeoutError:
                pass

    async def _poll_and_process(self) -> None:
        """Опрашивает БД и обрабатывает эпизоды."""
        self._stats.last_poll_at = datetime.utcnow()

        # Получаем эпизоды без медиа
        async with self._session_factory() as session:
            episodes = await repo.get_episodes_without_media(
                session,
                limit=self._batch_size,
            )

        if not episodes:
            logger.debug("No episodes to process")
            return

        logger.info("Found {} episodes to process", len(episodes))

        for ep in episodes:
            if self._shutdown_event.is_set():
                break

            await self._process_episode(ep)

    async def _process_episode(self, ep) -> None:
        """Обрабатывает один эпизод."""
        external_ids = (ep.anime.external_ids if ep.anime else {}) or {}

        if not external_ids:
            logger.warning("Episode {} has no external IDs, skipping", ep.id)
            self._stats.failed_count += 1
            return

        try:
            # Скачиваем с retry
            result = await retry_async(
                self._download_episode,
                ep,
                external_ids,
                max_retries=self._max_retries,
                delay=2.0,
                exceptions=(DownloadError,),
            )

            # Добавляем в очередь загрузки
            task = EpisodeUploadTask(
                episode_id=ep.id,
                anime_id=ep.anime_id,
                translation_id=ep.translation_id,
                number=ep.number,
                file_path=str(result.path),
                caption=self._build_caption(ep),
                quality=None,
                checksum=result.checksum,
                size_bytes=result.size_bytes,
            )

            await self._queue.enqueue(task)
            self._stats.processed_count += 1

            logger.info(
                "Enqueued episode {} for upload",
                ep.id,
            )

        except DownloadError as exc:
            logger.error(
                "Failed to download episode {}: {}",
                ep.id,
                exc,
            )
            self._stats.failed_count += 1

        except Exception as exc:
            logger.exception(
                "Unexpected error processing episode {}: {}",
                ep.id,
                exc,
            )
            self._stats.failed_count += 1

    async def _download_episode(self, ep, external_ids: dict) -> DownloadResult:
        """Скачивает эпизод."""
        return await self._downloader.download_episode(
            external_ids=external_ids,
            translation_id=ep.translation_id,
            episode_num=ep.number,
        )

    def _build_caption(self, ep) -> str:
        """Формирует caption для сообщения."""
        anime_title = ep.anime.title if ep.anime else ep.anime_id
        return f"{anime_title} — серия {ep.number}"

    @property
    def stats(self) -> WorkerStats:
        """Возвращает статистику worker."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Проверяет, запущен ли worker."""
        return not self._shutdown_event.is_set()


async def run_upload_worker() -> None:
    """
    Точка входа для запуска upload worker.

    Настраивает логирование и запускает worker.
    """
    setup_logging(
        level=settings.log_level,
        log_path=settings.log_file,
        json_format=settings.log_json,
    )

    worker = UploadWorker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(run_upload_worker())
