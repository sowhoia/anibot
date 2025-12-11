from datetime import datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import models


async def upsert_translation(session: AsyncSession, translation: dict) -> None:
    if not translation:
        return
    stmt = insert(models.Translation).values(**translation)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.Translation.id],
        set_={
            "title": stmt.excluded.title,
            "type": stmt.excluded.type,
        },
    )
    await session.execute(stmt)


async def upsert_anime(session: AsyncSession, anime: dict) -> None:
    stmt = insert(models.Anime).values(**anime)
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
            "updated_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)


async def upsert_anime_translation(session: AsyncSession, link: dict) -> None:
    stmt = insert(models.AnimeTranslation).values(**link)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.AnimeTranslation.anime_id, models.AnimeTranslation.translation_id],
        set_={
            "episodes_available": stmt.excluded.episodes_available,
            "last_episode": stmt.excluded.last_episode,
            "updated_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)


async def upsert_episodes(session: AsyncSession, episodes: Iterable[dict]) -> None:
    if not episodes:
        return
    stmt = insert(models.Episode).values(list(episodes))
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
            "updated_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)


async def mark_media(
    session: AsyncSession,
    episode_id: str,
    chat_id: str,
    message_id: int,
    file_unique_id: str | None,
    quality: int | None,
    source_url: str | None,
    checksum: str | None,
    size_bytes: int | None,
) -> None:
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
    await session.execute(stmt)


async def get_episodes_without_media(session: AsyncSession, limit: int = 20):
    q = (
        select(models.Episode)
        .join(models.Anime)
        .outerjoin(models.EpisodeMedia)
        .where(models.EpisodeMedia.episode_id.is_(None))
        .order_by(models.Anime.id, models.Episode.translation_id, models.Episode.number)
        .limit(limit)
        .options(selectinload(models.Episode.anime))
    )
    res = await session.execute(q)
    return res.scalars().all()


async def touch_user(session: AsyncSession, user_id: int, payload: dict) -> None:
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
            "last_seen_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)

