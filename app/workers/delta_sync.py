"""
Worker для дельта-синхронизации данных из Kodik.

Периодически получает обновления из API и импортирует их в БД.
"""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.common.async_utils import chunked, run_with_limited_concurrency
from app.common.logging import setup_logging
from app.config import settings
from app.db.session import get_session
from app.integrations.kodik import KodikClient, get_kodik_client
from app.services.ingest import IngestService


@dataclass
class SyncStats:
    """Статистика синхронизации."""

    started_at: datetime
    total_fetched: int = 0
    total_imported: int = 0
    failed_batches: int = 0
    last_sync_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "total_fetched": self.total_fetched,
            "total_imported": self.total_imported,
            "failed_batches": self.failed_batches,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }


class DeltaSyncWorker:
    """
    Worker для дельта-синхронизации данных из Kodik.

    Периодически получает обновления из API и импортирует их в БД.
    Поддерживает graceful shutdown и retry при ошибках.
    """

    def __init__(
        self,
        sync_interval: int = 3600,  # 1 час
        lookback_hours: int = 24,
        batch_size: int = 100,
        concurrency: int = 3,
    ) -> None:
        """
        Args:
            sync_interval: Интервал между синхронизациями (секунды)
            lookback_hours: На сколько часов назад смотреть
            batch_size: Размер батча для импорта
            concurrency: Количество параллельных батчей
        """
        self._sync_interval = sync_interval
        self._lookback_hours = lookback_hours
        self._batch_size = batch_size
        self._concurrency = concurrency

        self._client = get_kodik_client()
        self._ingest = IngestService(get_session())
        self._shutdown_event = asyncio.Event()
        self._stats = SyncStats(started_at=datetime.now(timezone.utc))

    async def start(self) -> None:
        """Запускает worker."""
        logger.info(
            "Starting delta sync worker (interval={}s, lookback={}h)",
            self._sync_interval,
            self._lookback_hours,
        )

        self._setup_signal_handlers()
        await self._run_loop()

    async def stop(self) -> None:
        """Останавливает worker."""
        logger.info("Stopping delta sync worker...")
        self._shutdown_event.set()
        logger.info("Delta sync worker stopped. Stats: {}", self._stats.to_dict())

    def _setup_signal_handlers(self) -> None:
        """Настраивает обработчики сигналов."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self._handle_signal(s)),
            )

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Обрабатывает сигнал остановки."""
        logger.info("Received signal {}, initiating shutdown...", sig.name)
        await self.stop()

    async def _run_loop(self) -> None:
        """Основной цикл worker."""
        while not self._shutdown_event.is_set():
            try:
                await self.sync()
            except Exception as exc:
                logger.exception("Error in sync loop: {}", exc)

            # Ждем следующей синхронизации или shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._sync_interval,
                )
            except asyncio.TimeoutError:
                pass

    async def sync(self, updated_since: datetime | str | None = None) -> SyncStats:
        """
        Выполняет синхронизацию.

        Args:
            updated_since: Дата начала (по умолчанию lookback_hours назад)

        Returns:
            Статистика синхронизации
        """
        if updated_since is None:
            updated_since = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)

        if isinstance(updated_since, datetime):
            ts = updated_since.isoformat()
        else:
            ts = updated_since

        logger.info("Starting delta sync (updated_since={})", ts)
        self._stats.last_sync_at = datetime.now(timezone.utc)

        try:
            # Получаем обновления
            raw_items = await self._client.fetch_delta(updated_since=ts)
            self._stats.total_fetched += len(raw_items)

            if not raw_items:
                logger.info("No updates since {}", ts)
                return self._stats

            logger.info("Fetched {} items for import", len(raw_items))

            # Разбиваем на батчи и импортируем
            batches = chunked(raw_items, self._batch_size)

            def on_error(exc: Exception, index: int) -> None:
                logger.error("Batch {} failed: {}", index, exc)
                self._stats.failed_batches += 1

            await run_with_limited_concurrency(
                batches=batches,
                concurrency=self._concurrency,
                worker=self._ingest.ingest_items,
                on_error=on_error,
                return_exceptions=True,
            )

            self._stats.total_imported += len(raw_items)
            logger.info(
                "Delta sync complete. Imported {} items ({} batches)",
                len(raw_items),
                len(batches),
            )

        except Exception as exc:
            logger.exception("Delta sync failed: {}", exc)
            raise

        return self._stats

    @property
    def stats(self) -> SyncStats:
        """Возвращает статистику."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Проверяет, запущен ли worker."""
        return not self._shutdown_event.is_set()


async def delta_sync(
    updated_at_from: str | None = None,
    concurrency: int = 3,
) -> None:
    """
    Выполняет разовую дельта-синхронизацию.

    Legacy функция для обратной совместимости.
    """
    setup_logging(
        level=settings.log_level,
        log_path=settings.log_file,
    )

    worker = DeltaSyncWorker(concurrency=concurrency)

    if updated_at_from:
        await worker.sync(updated_since=updated_at_from)
    else:
        await worker.sync()


async def run_delta_sync_worker() -> None:
    """Запускает delta sync worker в режиме демона."""
    setup_logging(
        level=settings.log_level,
        log_path=settings.log_file,
        json_format=settings.log_json,
    )

    worker = DeltaSyncWorker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(delta_sync())
