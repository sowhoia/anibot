"""
Клиент для работы с Kodik API.

Реализует:
- Rate limiting с токен-бакетом
- Автоматические retry при ошибках
- Пагинацию для получения полного каталога
- Дельта-синхронизацию по дате обновления
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, TypeAlias

import httpx
from anime_parsers_ru import KodikParserAsync
from loguru import logger

from app.config import settings


# URL для прямого API Kodik
KODIK_API_BASE = "https://kodikapi.com"


class KodikError(Exception):
    """Базовое исключение для ошибок Kodik API."""


class KodikRateLimitError(KodikError):
    """Превышен лимит запросов к API."""


class KodikNotFoundError(KodikError):
    """Запрошенный контент не найден."""


class KodikNetworkError(KodikError):
    """Сетевая ошибка при обращении к API."""


class ExternalIdType(str, Enum):
    """Типы внешних ID для идентификации аниме."""

    SHIKIMORI = "shikimori"
    KINOPOISK = "kinopoisk"
    IMDB = "imdb"


@dataclass(frozen=True, slots=True)
class ExternalId:
    """Внешний идентификатор аниме."""

    value: str
    type: ExternalIdType

    @classmethod
    def from_dict(cls, external_ids: dict[str, Any]) -> ExternalId:
        """
        Создает ExternalId из словаря, выбирая приоритетный ID.

        Приоритет: shikimori > kinopoisk > imdb
        """
        for id_type in ExternalIdType:
            val = external_ids.get(id_type.value)
            if val:
                return cls(value=str(val), type=id_type)
        raise KodikNotFoundError(
            "Нет доступных внешних ID (shikimori/kinopoisk/imdb)"
        )


# Type aliases для читаемости
KodikItem: TypeAlias = dict[str, Any]
KodikItems: TypeAlias = list[KodikItem]


class RateLimiter:
    """
    Token bucket rate limiter для контроля частоты запросов.

    Поддерживает burst-запросы и плавное ограничение.
    """

    __slots__ = ("_rate", "_capacity", "_tokens", "_last_refill", "_lock")

    def __init__(self, rate: float, capacity: int | None = None) -> None:
        """
        Args:
            rate: Максимальное количество запросов в секунду
            capacity: Максимальный размер bucket (по умолчанию = rate)
        """
        self._rate = rate
        self._capacity = capacity or int(rate)
        self._tokens = float(self._capacity)
        self._last_refill = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Ожидает доступный токен для выполнения запроса."""
        async with self._lock:
            await self._refill()
            while self._tokens < 1:
                wait_time = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                await self._refill()
            self._tokens -= 1

    async def _refill(self) -> None:
        """Пополняет bucket токенами на основе прошедшего времени."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


class KodikClient:
    """
    Клиент для работы с Kodik API.

    Особенности:
    - Автоматический rate limiting
    - Retry при временных ошибках
    - Пагинация для больших выборок
    - Поддержка дельта-синхронизации

    Примеры:
        >>> client = KodikClient()
        >>> items = await client.fetch_full_list(limit_per_page=100)
        >>> m3u8 = await client.get_episode_m3u8(
        ...     external_ids={"shikimori": "12345"},
        ...     translation_id=610,
        ...     episode_num=1
        ... )
    """

    # Конфигурация retry
    MAX_RETRIES: int = 3
    RETRY_DELAY_BASE: float = 1.0  # секунды, растет экспоненциально
    RETRY_EXCEPTIONS: tuple[type[Exception], ...] = (
        asyncio.TimeoutError,
        ConnectionError,
        OSError,
    )

    def __init__(
        self,
        token: str | None = None,
        rps_limit: int | None = None,
    ) -> None:
        """
        Args:
            token: API токен Kodik (по умолчанию из settings)
                  Если None или пустая строка, библиотека будет использовать публичные токены
            rps_limit: Лимит запросов в секунду (по умолчанию из settings)
        """
        # Если токен не указан, используем из settings (может быть None для публичных токенов)
        self._token = token if token is not None else settings.kodik_token
        # Если токен пустая строка, конвертируем в None для автоматического получения публичных
        if self._token == "":
            self._token = None
        self._parser = KodikParserAsync(token=self._token)
        self._rps_limit = rps_limit or settings.kodik_rps_limit
        self._rate_limiter = RateLimiter(rate=self._rps_limit)
        # Переиспользуемый httpx клиент для прямых API запросов
        self._http_client: httpx.AsyncClient | None = None

    async def fetch_full_list(
        self,
        limit_per_page: int = 50,
        max_pages: int | None = None,
    ) -> KodikItems:
        """
        Получает полный список аниме из Kodik.

        Args:
            limit_per_page: Количество элементов на страницу (1-100)
            max_pages: Максимальное количество страниц (None = без ограничений)

        Returns:
            Список всех материалов из каталога

        Raises:
            KodikError: При критической ошибке API
        """
        limit_per_page = max(1, min(100, limit_per_page))
        results: KodikItems = []
        next_page: str | None = None
        page_count = 0

        logger.info(
            "Starting full catalog fetch (limit_per_page={}, max_pages={})",
            limit_per_page,
            max_pages or "unlimited",
        )

        while True:
            batch, next_page = await self._fetch_page(
                limit_per_page=limit_per_page,
                start_from=next_page,
            )
            results.extend(batch)
            page_count += 1

            logger.debug(
                "Fetched page {} ({} items, total: {})",
                page_count,
                len(batch),
                len(results),
            )

            if not next_page:
                break
            if max_pages and page_count >= max_pages:
                logger.info("Reached max_pages limit ({})", max_pages)
                break

        logger.info(
            "Full catalog fetch complete: {} items from {} pages",
            len(results),
            page_count,
        )
        return results

    async def fetch_delta(
        self,
        updated_since: datetime | str,
        limit_per_page: int = 50,
        max_pages: int | None = None,
    ) -> KodikItems:
        """
        Получает материалы, обновленные после указанной даты.

        Note:
            API Kodik не поддерживает серверную фильтрацию по updated_at,
            поэтому фильтрация выполняется на клиенте после получения данных.
            Для эффективной дельта-синхронизации рекомендуется использовать
            сортировку по updated_at и ограничивать max_pages.

        Args:
            updated_since: Дата/время начала (ISO 8601 или datetime)
            limit_per_page: Количество элементов на страницу
            max_pages: Максимальное количество страниц

        Returns:
            Список материалов с updated_at >= updated_since
        """
        if isinstance(updated_since, datetime):
            updated_since_str = updated_since.isoformat()
        else:
            updated_since_str = updated_since

        logger.info("Starting delta fetch (updated_since={})", updated_since_str)

        items = await self.fetch_full_list(
            limit_per_page=limit_per_page,
            max_pages=max_pages,
        )

        filtered = [
            item
            for item in items
            if self._get_updated_at(item) >= updated_since_str
        ]

        logger.info(
            "Delta fetch complete: {} items match (from {} total)",
            len(filtered),
            len(items),
        )
        return filtered

    async def get_episode_m3u8(
        self,
        external_ids: dict[str, Any],
        translation_id: int,
        episode_num: int,
        quality: int = 720,
    ) -> str:
        """
        Получает m3u8 URL для конкретной серии.

        Args:
            external_ids: Словарь внешних ID (shikimori, kinopoisk, imdb)
            translation_id: ID озвучки
            episode_num: Номер серии
            quality: Качество видео (360, 480, 720, 1080)

        Returns:
            URL m3u8 плейлиста

        Raises:
            KodikNotFoundError: Если контент не найден
            KodikError: При других ошибках API
        """
        ext_id = ExternalId.from_dict(external_ids)

        logger.debug(
            "Getting m3u8 for {} {} ep{} tr{} q{}",
            ext_id.type.value,
            ext_id.value,
            episode_num,
            translation_id,
            quality,
        )

        return await self._with_retry(
            self._get_m3u8_internal,
            ext_id=ext_id,
            translation_id=translation_id,
            episode_num=episode_num,
            quality=quality,
        )

    async def _fetch_page(
        self,
        limit_per_page: int,
        start_from: str | None,
    ) -> tuple[KodikItems, str | None]:
        """Получает одну страницу результатов с retry."""
        return await self._with_retry(
            self._fetch_page_internal,
            limit_per_page=limit_per_page,
            start_from=start_from,
        )

    async def _fetch_page_internal(
        self,
        limit_per_page: int,
        start_from: str | None,
    ) -> tuple[KodikItems, str | None]:
        """
        Внутренний метод получения страницы.
        
        Использует прямой HTTP запрос к API Kodik для получения
        полных данных включая translation.
        """
        await self._rate_limiter.acquire()

        # Если есть токен, используем прямой API для полных данных
        if self._token:
            return await self._fetch_page_direct_api(limit_per_page, start_from)
        
        # Fallback на библиотеку если нет токена
        batch, next_from = await self._parser.get_list(
            limit_per_page=limit_per_page,
            pages_to_parse=1,
            include_material_data=True,
            only_anime=True,
            start_from=start_from,
        )
        return batch, next_from

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Возвращает переиспользуемый httpx клиент."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=30.0)
            )
        return self._http_client

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _fetch_page_direct_api(
        self,
        limit_per_page: int,
        start_from: str | None,
    ) -> tuple[KodikItems, str | None]:
        """
        Получает страницу напрямую через API Kodik.

        Возвращает полные данные включая translation с id, title, type.
        """
        from urllib.parse import parse_qs, urlparse

        params = {
            "token": self._token,
            "limit": limit_per_page,
            "types": "anime,anime-serial",
            "with_material_data": "true",
            "with_episodes": "true",
            "sort": "updated_at",
            "order": "desc",
        }

        if start_from:
            # start_from - это URL следующей страницы или параметр next
            if start_from.startswith("http"):
                # Это полный URL, извлекаем параметр next
                parsed = urlparse(start_from)
                qs = parse_qs(parsed.query)
                if "next" in qs:
                    params["next"] = qs["next"][0]
            else:
                params["next"] = start_from

        client = await self._get_http_client()
        for attempt in range(3):
            try:
                response = await client.get(f"{KODIK_API_BASE}/list", params=params)
                response.raise_for_status()
                data = response.json()
                break
            except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                if attempt == 2:
                    raise
                logger.warning("Kodik API timeout, retry {}/3: {}", attempt + 1, e)
                await asyncio.sleep(2 ** attempt)

        results = data.get("results", [])
        next_page = data.get("next_page")

        # Извлекаем параметр next из next_page URL
        next_from = None
        if next_page:
            parsed = urlparse(next_page)
            qs = parse_qs(parsed.query)
            if "next" in qs:
                next_from = qs["next"][0]

        return results, next_from

    async def _get_m3u8_internal(
        self,
        ext_id: ExternalId,
        translation_id: int,
        episode_num: int,
        quality: int,
    ) -> str:
        """Внутренний метод получения m3u8."""
        await self._rate_limiter.acquire()

        return await self._parser.get_m3u8_playlist_link(
            id=ext_id.value,
            id_type=ext_id.type.value,
            translation_id=str(translation_id),
            seria_num=episode_num,
            quality=quality,
        )

    async def _with_retry(self, func, *args, **kwargs) -> Any:
        """
        Выполняет функцию с автоматическим retry при ошибках.

        Использует экспоненциальный backoff между попытками.
        """
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await func(*args, **kwargs)
            except self.RETRY_EXCEPTIONS as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Attempt {}/{} failed: {}. Retrying in {:.1f}s",
                        attempt,
                        self.MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "All {} attempts failed. Last error: {}",
                        self.MAX_RETRIES,
                        exc,
                    )

        raise KodikNetworkError(
            f"Failed after {self.MAX_RETRIES} attempts"
        ) from last_error

    @staticmethod
    def _get_updated_at(item: KodikItem) -> str:
        """Извлекает updated_at из элемента (dict или объект)."""
        if isinstance(item, dict):
            return item.get("updated_at", "")
        return getattr(item, "updated_at", "") or ""


# Создаем singleton клиент для удобства использования
_client: KodikClient | None = None


def get_kodik_client() -> KodikClient:
    """Возвращает singleton экземпляр KodikClient."""
    global _client
    if _client is None:
        _client = KodikClient()
    return _client
