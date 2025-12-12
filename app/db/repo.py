"""
Репозиторий для работы с базой данных.

Предоставляет унифицированный интерфейс для CRUD операций
с поддержкой batch upsert и оптимизированных запросов.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import models


def utc_now() -> datetime:
    """
    Возвращает текущее время в UTC без timezone info.
    
    Используется для колонок TIMESTAMP WITHOUT TIME ZONE в PostgreSQL.
    Все времена хранятся в UTC, но без явного указания timezone.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AnimeRepository:
    """Репозиторий для работы с аниме и связанными сущностями."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ==================== Translations ====================

    async def upsert_translation(self, data: dict[str, Any]) -> None:
        """
        Создает или обновляет озвучку.

        Args:
            data: Словарь с полями id, title, type
        """
        if not data or not data.get("id"):
            return

        stmt = insert(models.Translation).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.Translation.id],
            set_={
                "title": stmt.excluded.title,
                "type": stmt.excluded.type,
            },
        )
        await self._session.execute(stmt)

    async def upsert_translations_batch(
        self,
        translations: Sequence[dict[str, Any]],
    ) -> int:
        """
        Batch upsert озвучек.

        Returns:
            Количество обработанных записей
        """
        if not translations:
            return 0

        # Фильтруем невалидные записи
        valid = [t for t in translations if t and t.get("id")]
        if not valid:
            return 0

        stmt = insert(models.Translation).values(valid)
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.Translation.id],
            set_={
                "title": stmt.excluded.title,
                "type": stmt.excluded.type,
            },
        )
        await self._session.execute(stmt)
        return len(valid)

    # ==================== Anime ====================

    async def upsert_anime(self, data: dict[str, Any]) -> None:
        """
        Создает или обновляет аниме.

        Args:
            data: Словарь с данными аниме
        """
        if not data or not data.get("id"):
            return

        stmt = insert(models.Anime).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.Anime.id],
            set_={
                "title": stmt.excluded.title,
                "title_orig": stmt.excluded.title_orig,
                "alt_titles": stmt.excluded.alt_titles,
                "year": stmt.excluded.year,
                "poster_url": stmt.excluded.poster_url,
                "description": stmt.excluded.description,
                "genres": stmt.excluded.genres,
                "rating_shiki": stmt.excluded.rating_shiki,
                "rating_kinopoisk": stmt.excluded.rating_kinopoisk,
                "rating_imdb": stmt.excluded.rating_imdb,
                "episodes_total": stmt.excluded.episodes_total,
                "external_ids": stmt.excluded.external_ids,
                "blocked_countries": stmt.excluded.blocked_countries,
                "status": stmt.excluded.status,
                "updated_at": utc_now(),
            },
        )
        await self._session.execute(stmt)

    async def upsert_anime_batch(
        self,
        anime_list: Sequence[dict[str, Any]],
    ) -> int:
        """
        Batch upsert аниме.

        Returns:
            Количество обработанных записей
        """
        if not anime_list:
            return 0

        valid = [a for a in anime_list if a and a.get("id")]
        if not valid:
            return 0

        stmt = insert(models.Anime).values(valid)
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.Anime.id],
            set_={
                "title": stmt.excluded.title,
                "title_orig": stmt.excluded.title_orig,
                "alt_titles": stmt.excluded.alt_titles,
                "year": stmt.excluded.year,
                "poster_url": stmt.excluded.poster_url,
                "description": stmt.excluded.description,
                "genres": stmt.excluded.genres,
                "rating_shiki": stmt.excluded.rating_shiki,
                "rating_kinopoisk": stmt.excluded.rating_kinopoisk,
                "rating_imdb": stmt.excluded.rating_imdb,
                "episodes_total": stmt.excluded.episodes_total,
                "external_ids": stmt.excluded.external_ids,
                "blocked_countries": stmt.excluded.blocked_countries,
                "status": stmt.excluded.status,
                "updated_at": utc_now(),
            },
        )
        await self._session.execute(stmt)
        return len(valid)

    async def get_anime_by_id(self, anime_id: str) -> models.Anime | None:
        """Получает аниме по ID."""
        result = await self._session.execute(
            select(models.Anime).where(models.Anime.id == anime_id)
        )
        return result.scalar_one_or_none()

    async def get_anime_count(self) -> int:
        """Возвращает общее количество аниме в базе."""
        result = await self._session.execute(
            select(func.count()).select_from(models.Anime)
        )
        return result.scalar() or 0

    # ==================== Anime Translations ====================

    async def upsert_anime_translation(self, data: dict[str, Any]) -> None:
        """Создает или обновляет связь аниме-озвучка."""
        if not data or not data.get("anime_id") or not data.get("translation_id"):
            return

        stmt = insert(models.AnimeTranslation).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                models.AnimeTranslation.anime_id,
                models.AnimeTranslation.translation_id,
            ],
            set_={
                "episodes_available": stmt.excluded.episodes_available,
                "last_episode": stmt.excluded.last_episode,
                "updated_at": utc_now(),
            },
        )
        await self._session.execute(stmt)

    async def upsert_anime_translations_batch(
        self,
        links: Sequence[dict[str, Any]],
    ) -> int:
        """Batch upsert связей аниме-озвучка."""
        if not links:
            return 0

        valid = [
            ln
            for ln in links
            if ln and ln.get("anime_id") and ln.get("translation_id")
        ]
        if not valid:
            return 0

        stmt = insert(models.AnimeTranslation).values(valid)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                models.AnimeTranslation.anime_id,
                models.AnimeTranslation.translation_id,
            ],
            set_={
                "episodes_available": stmt.excluded.episodes_available,
                "last_episode": stmt.excluded.last_episode,
                "updated_at": utc_now(),
            },
        )
        await self._session.execute(stmt)
        return len(valid)

    # ==================== Episodes ====================

    async def upsert_episodes(self, episodes: Sequence[dict[str, Any]]) -> int:
        """
        Batch upsert эпизодов.

        Returns:
            Количество обработанных записей
        """
        if not episodes:
            return 0

        valid = [e for e in episodes if e and e.get("id")]
        if not valid:
            return 0

        stmt = insert(models.Episode).values(valid)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                models.Episode.anime_id,
                models.Episode.translation_id,
                models.Episode.number,
            ],
            set_={
                "title": stmt.excluded.title,
                "season": stmt.excluded.season,
                "duration": stmt.excluded.duration,
                "preview_image": stmt.excluded.preview_image,
                "updated_at": utc_now(),
            },
        )
        await self._session.execute(stmt)
        return len(valid)

    async def get_episodes_without_media(
        self,
        limit: int = 20,
    ) -> list[models.Episode]:
        """
        Получает эпизоды без загруженного медиа.

        Args:
            limit: Максимальное количество записей

        Returns:
            Список эпизодов с загруженными связями anime
        """
        query = (
            select(models.Episode)
            .join(models.Anime)
            .outerjoin(models.EpisodeMedia)
            .where(models.EpisodeMedia.episode_id.is_(None))
            .order_by(
                models.Anime.id,
                models.Episode.translation_id,
                models.Episode.number,
            )
            .limit(limit)
            .options(selectinload(models.Episode.anime))
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_episode_by_id(self, episode_id: str) -> models.Episode | None:
        """Получает эпизод по ID с загруженными связями."""
        result = await self._session.execute(
            select(models.Episode)
            .where(models.Episode.id == episode_id)
            .options(
                selectinload(models.Episode.anime),
                selectinload(models.Episode.media),
            )
        )
        return result.scalar_one_or_none()

    # ==================== Episode Media ====================

    async def mark_media(
        self,
        episode_id: str,
        chat_id: str,
        message_id: int,
        file_unique_id: str | None = None,
        quality: int | None = None,
        source_url: str | None = None,
        checksum: str | None = None,
        size_bytes: int | None = None,
    ) -> None:
        """
        Создает или обновляет запись медиа для эпизода.

        Args:
            episode_id: ID эпизода
            chat_id: ID чата в Telegram
            message_id: ID сообщения в Telegram
            file_unique_id: Уникальный ID файла в Telegram
            quality: Качество видео
            source_url: URL источника
            checksum: Контрольная сумма файла
            size_bytes: Размер файла в байтах
        """
        stmt = insert(models.EpisodeMedia).values(
            episode_id=episode_id,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            file_unique_id=file_unique_id,
            quality=quality,
            source_url=source_url,
            checksum=checksum,
            size_bytes=size_bytes,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.EpisodeMedia.episode_id],
            set_={
                "telegram_chat_id": stmt.excluded.telegram_chat_id,
                "telegram_message_id": stmt.excluded.telegram_message_id,
                "file_unique_id": stmt.excluded.file_unique_id,
                "quality": stmt.excluded.quality,
                "source_url": stmt.excluded.source_url,
                "checksum": stmt.excluded.checksum,
                "size_bytes": stmt.excluded.size_bytes,
            },
        )
        await self._session.execute(stmt)

    # ==================== Users ====================

    async def touch_user(self, user_id: int, payload: dict[str, Any]) -> None:
        """
        Создает или обновляет пользователя.

        Args:
            user_id: Telegram user ID
            payload: Данные пользователя
        """
        stmt = insert(models.User).values(id=user_id, **payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.User.id],
            set_={
                "username": stmt.excluded.username,
                "first_name": stmt.excluded.first_name,
                "last_name": stmt.excluded.last_name,
                "language_code": stmt.excluded.language_code,
                "is_premium": stmt.excluded.is_premium,
                "geo": stmt.excluded.geo,
                "last_seen_at": utc_now(),
            },
        )
        await self._session.execute(stmt)

    async def get_user_by_id(self, user_id: int) -> models.User | None:
        """Получает пользователя по ID."""
        result = await self._session.execute(
            select(models.User).where(models.User.id == user_id)
        )
        return result.scalar_one_or_none()

    # ==================== Favorites ====================

    async def add_favorite(self, user_id: int, anime_id: str) -> None:
        """Добавляет аниме в избранное пользователя."""
        stmt = insert(models.Favorite).values(
            user_id=user_id,
            anime_id=anime_id,
        )
        stmt = stmt.on_conflict_do_nothing()
        await self._session.execute(stmt)

    async def remove_favorite(self, user_id: int, anime_id: str) -> bool:
        """
        Удаляет аниме из избранного.

        Returns:
            True если запись была удалена, False если её не было
        """
        result = await self._session.execute(
            delete(models.Favorite).where(
                models.Favorite.user_id == user_id,
                models.Favorite.anime_id == anime_id,
            )
        )
        return result.rowcount > 0

    async def get_user_favorites(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[models.Anime]:
        """Получает список избранных аниме пользователя."""
        result = await self._session.execute(
            select(models.Anime)
            .join(models.Favorite)
            .where(models.Favorite.user_id == user_id)
            .order_by(models.Favorite.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def is_favorite(self, user_id: int, anime_id: str) -> bool:
        """Проверяет, находится ли аниме в избранном."""
        result = await self._session.execute(
            select(func.count())
            .select_from(models.Favorite)
            .where(
                models.Favorite.user_id == user_id,
                models.Favorite.anime_id == anime_id,
            )
        )
        return (result.scalar() or 0) > 0

    # ==================== Ratings ====================

    async def set_rating(self, user_id: int, anime_id: str, score: int) -> None:
        """
        Устанавливает оценку аниме от пользователя.

        Args:
            user_id: ID пользователя
            anime_id: ID аниме
            score: Оценка от 1 до 10
        """
        if not 1 <= score <= 10:
            raise ValueError("Score must be between 1 and 10")

        stmt = insert(models.Rating).values(
            user_id=user_id,
            anime_id=anime_id,
            score=score,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.Rating.user_id, models.Rating.anime_id],
            set_={"score": score},
        )
        await self._session.execute(stmt)

    async def get_user_rating(
        self,
        user_id: int,
        anime_id: str,
    ) -> int | None:
        """Получает оценку пользователя для аниме."""
        result = await self._session.execute(
            select(models.Rating.score).where(
                models.Rating.user_id == user_id,
                models.Rating.anime_id == anime_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_anime_avg_rating(self, anime_id: str) -> float | None:
        """Получает среднюю оценку аниме от пользователей."""
        result = await self._session.execute(
            select(func.avg(models.Rating.score)).where(
                models.Rating.anime_id == anime_id
            )
        )
        return result.scalar_one_or_none()

    # ==================== Watch History ====================

    async def update_watch_progress(
        self,
        user_id: int,
        episode_id: str,
        progress_seconds: int = 0,
        completed: bool = False,
    ) -> None:
        """
        Обновляет прогресс просмотра эпизода.

        Args:
            user_id: ID пользователя
            episode_id: ID эпизода
            progress_seconds: Прогресс в секундах
            completed: Просмотрен ли эпизод полностью
        """
        stmt = insert(models.WatchHistory).values(
            user_id=user_id,
            episode_id=episode_id,
            progress_seconds=progress_seconds,
            completed=completed,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                models.WatchHistory.user_id,
                models.WatchHistory.episode_id,
            ],
            set_={
                "progress_seconds": progress_seconds,
                "completed": completed,
                "watched_at": utc_now(),
            },
        )
        await self._session.execute(stmt)

    async def get_watch_progress(
        self,
        user_id: int,
        episode_id: str,
    ) -> models.WatchHistory | None:
        """Получает прогресс просмотра эпизода."""
        result = await self._session.execute(
            select(models.WatchHistory).where(
                models.WatchHistory.user_id == user_id,
                models.WatchHistory.episode_id == episode_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_user_watch_history(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        only_completed: bool = False,
    ) -> list[models.WatchHistory]:
        """
        Получает историю просмотра пользователя.

        Args:
            user_id: ID пользователя
            limit: Максимальное количество записей
            offset: Смещение
            only_completed: Только завершенные просмотры

        Returns:
            Список записей истории с загруженными эпизодами
        """
        query = (
            select(models.WatchHistory)
            .where(models.WatchHistory.user_id == user_id)
            .order_by(models.WatchHistory.watched_at.desc())
            .offset(offset)
            .limit(limit)
            .options(selectinload(models.WatchHistory.episode))
        )

        if only_completed:
            query = query.where(models.WatchHistory.completed.is_(True))

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_anime_watched_count(
        self,
        user_id: int,
        anime_id: str,
    ) -> int:
        """Получает количество просмотренных эпизодов аниме пользователем."""
        result = await self._session.execute(
            select(func.count())
            .select_from(models.WatchHistory)
            .join(models.Episode)
            .where(
                models.WatchHistory.user_id == user_id,
                models.Episode.anime_id == anime_id,
                models.WatchHistory.completed.is_(True),
            )
        )
        return result.scalar() or 0
