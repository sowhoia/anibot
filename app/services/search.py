"""
Сервис поиска аниме.

Особенности:
- Полнотекстовый поиск с trigram similarity
- Кэширование результатов в Redis
- Оптимизированные SQL-запросы
- Пагинация результатов
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy import func, literal, select, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import models


@dataclass(frozen=True, slots=True)
class SearchItem:
    """Элемент результата поиска."""

    id: str
    title: str
    title_orig: str | None = None
    year: int | None = None
    poster_url: str | None = None
    rating: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Преобразует в словарь."""
        return {
            "id": self.id,
            "title": self.title,
            "title_orig": self.title_orig,
            "year": self.year,
            "poster_url": self.poster_url,
            "rating": self.rating,
        }


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Результат поиска с метаданными."""

    items: list[SearchItem]
    total: int
    page: int
    limit: int
    query: str

    @property
    def total_pages(self) -> int:
        """Общее количество страниц."""
        return (self.total + self.limit - 1) // self.limit if self.limit > 0 else 0

    @property
    def has_next(self) -> bool:
        """Есть ли следующая страница."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Есть ли предыдущая страница."""
        return self.page > 1


class SearchCache:
    """
    Кэш для результатов поиска.

    Использует Redis для хранения результатов с TTL.
    """

    PREFIX = "search:"

    def __init__(self, redis_url: str, ttl: int = 3600) -> None:
        """
        Args:
            redis_url: URL подключения к Redis
            ttl: Время жизни кэша в секундах
        """
        self._redis_url = redis_url
        self._ttl = ttl
        self._redis = None

    async def _get_redis(self):
        """Lazy initialization Redis клиента."""
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.from_url(self._redis_url)
        return self._redis

    def _make_key(self, query: str, page: int, limit: int) -> str:
        """Генерирует ключ кэша."""
        data = f"{query.lower().strip()}:{page}:{limit}"
        hash_val = hashlib.md5(data.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{hash_val}"

    async def get(
        self,
        query: str,
        page: int,
        limit: int,
    ) -> tuple[list[SearchItem], int] | None:
        """
        Получает результат из кэша.

        Returns:
            (items, total) или None если кэш пуст
        """
        try:
            redis = await self._get_redis()
            key = self._make_key(query, page, limit)
            data = await redis.get(key)

            if data is None:
                return None

            parsed = json.loads(data)
            items = [SearchItem(**item) for item in parsed["items"]]
            return items, parsed["total"]

        except Exception as exc:
            logger.warning("Cache get failed: {}", exc)
            return None

    async def set(
        self,
        query: str,
        page: int,
        limit: int,
        items: list[SearchItem],
        total: int,
    ) -> None:
        """Сохраняет результат в кэш."""
        try:
            redis = await self._get_redis()
            key = self._make_key(query, page, limit)
            data = json.dumps({
                "items": [item.to_dict() for item in items],
                "total": total,
            })
            await redis.setex(key, self._ttl, data)

        except Exception as exc:
            logger.warning("Cache set failed: {}", exc)

    async def invalidate(self, pattern: str = "*") -> int:
        """
        Инвалидирует кэш по паттерну.

        Returns:
            Количество удаленных ключей
        """
        try:
            redis = await self._get_redis()
            keys = []
            async for key in redis.scan_iter(f"{self.PREFIX}{pattern}"):
                keys.append(key)

            if keys:
                return await redis.delete(*keys)
            return 0

        except Exception as exc:
            logger.warning("Cache invalidate failed: {}", exc)
            return 0

    async def close(self) -> None:
        """Закрывает соединение с Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class SearchService:
    """
    Сервис поиска аниме.

    Особенности:
    - Поиск по названию и оригинальному названию
    - Trigram similarity для нечеткого поиска
    - Кэширование результатов
    - Сортировка по релевантности и году

    Примеры:
        >>> service = SearchService()
        >>> result = await service.search("Наруто", page=1, limit=10)
        >>> for item in result.items:
        ...     print(f"{item.title} ({item.year})")
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        cache: SearchCache | None = None,
        cache_enabled: bool | None = None,
    ) -> None:
        """
        Args:
            session_factory: Фабрика сессий SQLAlchemy
            cache: Экземпляр кэша (опционально)
            cache_enabled: Включить кэширование (по умолчанию из settings)
        """
        from app.db.session import get_session

        self._session_factory = session_factory or get_session()
        self._cache_enabled = (
            cache_enabled
            if cache_enabled is not None
            else settings.search_cache_enabled
        )

        if self._cache_enabled:
            self._cache = cache or SearchCache(
                redis_url=settings.redis_url,
                ttl=settings.redis_cache_ttl,
            )
        else:
            self._cache = None

    async def search(
        self,
        query: str,
        page: int = 1,
        limit: int | None = None,
    ) -> SearchResult:
        """
        Выполняет поиск аниме.

        Args:
            query: Поисковый запрос
            page: Номер страницы (начиная с 1)
            limit: Количество результатов на страницу

        Returns:
            SearchResult с найденными элементами и метаданными
        """
        query = query.strip()
        page = max(1, page)
        limit = limit or settings.search_results_per_page

        if not query:
            return SearchResult(
                items=[],
                total=0,
                page=page,
                limit=limit,
                query=query,
            )

        # Проверяем кэш
        if self._cache:
            cached = await self._cache.get(query, page, limit)
            if cached is not None:
                items, total = cached
                logger.debug("Cache hit for query: {}", query)
                return SearchResult(
                    items=items,
                    total=total,
                    page=page,
                    limit=limit,
                    query=query,
                )

        # Выполняем поиск
        async with self._session_factory() as session:
            items, total = await self._execute_search(session, query, page, limit)

        # Сохраняем в кэш
        if self._cache:
            await self._cache.set(query, page, limit, items, total)

        return SearchResult(
            items=items,
            total=total,
            page=page,
            limit=limit,
            query=query,
        )

    async def _execute_search(
        self,
        session: AsyncSession,
        query: str,
        page: int,
        limit: int,
    ) -> tuple[list[SearchItem], int]:
        """Выполняет поисковый запрос к БД."""
        # Подготавливаем паттерн для ILIKE
        pattern = f"%{query}%"

        # Вычисляем similarity score
        similarity = func.coalesce(
            func.similarity(models.Anime.title, query),
            literal(0.0),
        )

        # Определяем лучший рейтинг из доступных
        best_rating = func.coalesce(
            models.Anime.rating_shiki,
            models.Anime.rating_kinopoisk,
            models.Anime.rating_imdb,
        )

        # Основной запрос
        base_query = (
            select(
                models.Anime.id,
                models.Anime.title,
                models.Anime.title_orig,
                models.Anime.year,
                models.Anime.poster_url,
                best_rating.label("rating"),
                similarity.label("sim"),
            )
            .where(
                or_(
                    models.Anime.title.ilike(pattern),
                    models.Anime.title_orig.ilike(pattern),
                )
            )
        )

        # Считаем общее количество
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Получаем результаты с пагинацией и сортировкой
        offset = (page - 1) * limit
        results_query = (
            base_query
            .order_by(
                similarity.desc(),
                models.Anime.year.desc().nullslast(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(results_query)
        rows = result.all()

        items = [
            SearchItem(
                id=row.id,
                title=row.title,
                title_orig=row.title_orig,
                year=row.year,
                poster_url=row.poster_url,
                rating=row.rating,
            )
            for row in rows
        ]

        logger.debug(
            "Search '{}': {} results (page {}/{})",
            query,
            total,
            page,
            (total + limit - 1) // limit if limit > 0 else 0,
        )

        return items, total

    async def close(self) -> None:
        """Закрывает ресурсы сервиса."""
        if self._cache:
            await self._cache.close()


# Singleton сервис для удобства
_service: SearchService | None = None


def get_search_service() -> SearchService:
    """Возвращает singleton экземпляр SearchService."""
    global _service
    if _service is None:
        _service = SearchService()
    return _service
