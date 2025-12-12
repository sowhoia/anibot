"""
Сервис импорта данных из Kodik в базу данных.

Обрабатывает нормализацию и сохранение данных с поддержкой
batch операций и обработки ошибок.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repo import AnimeRepository
from app.services.normalizer import NormalizedAnimeBundle, normalize_kodik_item


@dataclass
class IngestStats:
    """Статистика импорта."""

    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    errors: list[tuple[str | None, str]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class IngestService:
    """
    Сервис импорта данных из Kodik API в базу данных.

    Особенности:
    - Нормализация данных из различных форматов API
    - Batch upsert операции для эффективности
    - Обработка ошибок с продолжением импорта
    - Детальное логирование

    Примеры:
        >>> service = IngestService(session_factory)
        >>> stats = await service.ingest_items(raw_items)
        >>> print(f"Imported {stats.successful}/{stats.total_processed}")
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """
        Args:
            session_factory: Фабрика сессий SQLAlchemy
        """
        self._session_factory = session_factory

    async def ingest_items(
        self,
        raw_items: Iterable[Any],
        continue_on_error: bool = True,
    ) -> IngestStats:
        """
        Импортирует элементы в базу данных.

        Args:
            raw_items: Итерируемый объект сырых данных из API
            continue_on_error: Продолжать при ошибках отдельных элементов

        Returns:
            Статистика импорта
        """
        stats = IngestStats()
        bundles: list[NormalizedAnimeBundle] = []

        # Нормализуем данные
        for raw in raw_items:
            stats.total_processed += 1
            try:
                bundle = normalize_kodik_item(raw)
                bundles.append(bundle)
            except Exception as exc:
                raw_id = self._extract_id(raw)
                error_msg = str(exc)
                stats.errors.append((raw_id, error_msg))
                stats.failed += 1

                if continue_on_error:
                    logger.warning(
                        "Failed to normalize item {}: {}",
                        raw_id,
                        error_msg,
                    )
                else:
                    raise

        # Сохраняем в БД
        if bundles:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._persist_bundles(session, bundles, stats)

        logger.info(
            "Ingest complete: {}/{} successful, {} failed",
            stats.successful,
            stats.total_processed,
            stats.failed,
        )

        return stats

    async def ingest_single(self, raw_item: Any) -> NormalizedAnimeBundle:
        """
        Импортирует один элемент.

        Args:
            raw_item: Сырые данные из API

        Returns:
            Нормализованный bundle

        Raises:
            Exception: При ошибке нормализации или сохранения
        """
        bundle = normalize_kodik_item(raw_item)

        async with self._session_factory() as session:
            async with session.begin():
                await self._persist_bundle(session, bundle)

        return bundle

    async def _persist_bundles(
        self,
        session: AsyncSession,
        bundles: list[NormalizedAnimeBundle],
        stats: IngestStats,
    ) -> None:
        """Сохраняет список bundles в БД."""
        repo = AnimeRepository(session)

        for bundle in bundles:
            try:
                await self._persist_bundle_with_repo(repo, bundle)
                stats.successful += 1
            except Exception as exc:
                anime_id = bundle.anime.get("id")
                error_msg = str(exc)
                stats.errors.append((anime_id, error_msg))
                stats.failed += 1
                logger.warning(
                    "Failed to persist bundle {}: {}",
                    anime_id,
                    error_msg,
                )

    async def _persist_bundle(
        self,
        session: AsyncSession,
        bundle: NormalizedAnimeBundle,
    ) -> None:
        """Сохраняет один bundle в БД (legacy метод)."""
        repo = AnimeRepository(session)
        await self._persist_bundle_with_repo(repo, bundle)

    async def _persist_bundle_with_repo(
        self,
        repo: AnimeRepository,
        bundle: NormalizedAnimeBundle,
    ) -> None:
        """Сохраняет bundle используя репозиторий."""
        # Сначала сохраняем озвучку (FK для anime_translation)
        await repo.upsert_translation(bundle.translation)

        # Затем аниме
        await repo.upsert_anime(bundle.anime)

        # Связь аниме-озвучка
        await repo.upsert_anime_translation(bundle.anime_translation)

        # Эпизоды
        if bundle.episodes:
            episodes_data = [ep.to_dict() for ep in bundle.episodes]
            await repo.upsert_episodes(episodes_data)

        logger.debug(
            "Persisted bundle: anime={} translation={} episodes={}",
            bundle.anime.get("id"),
            bundle.translation.get("id"),
            len(bundle.episodes),
        )

    @staticmethod
    def _extract_id(raw: Any) -> str | None:
        """Извлекает ID из сырых данных для логирования."""
        if isinstance(raw, dict):
            return raw.get("id") or raw.get("kodik_id")
        return getattr(raw, "id", None)
