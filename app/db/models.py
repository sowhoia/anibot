"""
Модели базы данных SQLAlchemy 2.0.

Определяет схему БД для хранения аниме, переводов, эпизодов и пользователей.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
        list[int]: JSONB,
    }


class TimestampMixin:
    """Миксин для полей created_at и updated_at."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Anime(TimestampMixin, Base):
    """
    Модель аниме.

    Хранит основную информацию об аниме: названия, рейтинги,
    внешние идентификаторы для интеграций.
    """

    __tablename__ = "anime"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    title_orig: Mapped[str | None] = mapped_column(String(512))
    alt_titles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer)
    poster_url: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    genres: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Рейтинги
    rating_shiki: Mapped[float | None] = mapped_column(Float)
    rating_kinopoisk: Mapped[float | None] = mapped_column(Float)
    rating_imdb: Mapped[float | None] = mapped_column(Float)

    episodes_total: Mapped[int | None] = mapped_column(Integer)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    blocked_countries: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Статус (ongoing, released, announced)
    status: Mapped[str | None] = mapped_column(String(32))

    # Relationships
    translations: Mapped[list[AnimeTranslation]] = relationship(
        back_populates="anime",
        cascade="all, delete-orphan",
    )
    episodes: Mapped[list[Episode]] = relationship(
        back_populates="anime",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_anime_title", "title"),
        Index("ix_anime_title_orig", "title_orig"),
        Index("ix_anime_year", "year"),
        Index("ix_anime_status", "status"),
        Index("ix_anime_updated_at", "updated_at"),
        # GIN индекс для поиска по alt_titles
        Index(
            "ix_anime_alt_titles_gin",
            "alt_titles",
            postgresql_using="gin",
        ),
        # GIN индекс для поиска по жанрам
        Index(
            "ix_anime_genres_gin",
            "genres",
            postgresql_using="gin",
        ),
        # Частичный индекс для активных аниме
        Index(
            "ix_anime_year_rating",
            "year",
            "rating_shiki",
            postgresql_where="rating_shiki IS NOT NULL",
        ),
    )

    def __repr__(self) -> str:
        return f"<Anime(id={self.id!r}, title={self.title!r})>"


class Translation(Base):
    """
    Модель студии озвучки/субтитров.

    Хранит информацию о переводчиках.
    """

    __tablename__ = "translation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    type: Mapped[str | None] = mapped_column(String(32))  # voice, subtitles

    # Relationships
    anime_links: Mapped[list[AnimeTranslation]] = relationship(
        back_populates="translation",
    )

    __table_args__ = (
        Index("ix_translation_type", "type"),
    )

    def __repr__(self) -> str:
        return f"<Translation(id={self.id}, title={self.title!r})>"


class AnimeTranslation(Base):
    """
    Связь аниме и озвучки.

    Хранит информацию о доступных эпизодах для конкретной озвучки.
    """

    __tablename__ = "anime_translation"

    anime_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("anime.id", ondelete="CASCADE"),
        primary_key=True,
    )
    translation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("translation.id", ondelete="CASCADE"),
        primary_key=True,
    )
    episodes_available: Mapped[int] = mapped_column(Integer, default=0)
    last_episode: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    anime: Mapped[Anime] = relationship(back_populates="translations")
    translation: Mapped[Translation] = relationship(back_populates="anime_links")

    __table_args__ = (
        Index("ix_anime_translation_translation_id", "translation_id"),
        Index("ix_anime_translation_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<AnimeTranslation(anime_id={self.anime_id!r}, translation_id={self.translation_id})>"


class Episode(Base):
    """
    Модель эпизода.

    Хранит информацию об отдельном эпизоде аниме.
    """

    __tablename__ = "episode"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    anime_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("anime.id", ondelete="CASCADE"),
        nullable=False,
    )
    translation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("translation.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str | None] = mapped_column(String(512))
    duration: Mapped[int | None] = mapped_column(Integer)  # в секундах
    preview_image: Mapped[str | None] = mapped_column(String(1024))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    anime: Mapped[Anime] = relationship(back_populates="episodes")
    translation: Mapped[Translation] = relationship()
    media: Mapped[EpisodeMedia | None] = relationship(
        back_populates="episode",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "anime_id",
            "translation_id",
            "number",
            name="uq_episode_number",
        ),
        Index("ix_episode_anime_translation", "anime_id", "translation_id"),
        Index("ix_episode_translation_number", "translation_id", "number"),
        Index("ix_episode_updated_at", "updated_at"),
        CheckConstraint("number > 0", name="ck_episode_number_positive"),
        CheckConstraint("season > 0", name="ck_episode_season_positive"),
    )

    def __repr__(self) -> str:
        return f"<Episode(id={self.id!r}, anime_id={self.anime_id!r}, number={self.number})>"


class EpisodeMedia(Base):
    """
    Модель медиа-файла эпизода.

    Хранит ссылку на загруженное видео в Telegram.
    """

    __tablename__ = "episode_media"

    episode_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("episode.id", ondelete="CASCADE"),
        primary_key=True,
    )
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(String(128))
    quality: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    checksum: Mapped[str | None] = mapped_column(String(64))  # SHA256
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
    )

    # Relationships
    episode: Mapped[Episode] = relationship(back_populates="media")

    __table_args__ = (
        Index("ix_episode_media_chat_message", "telegram_chat_id", "telegram_message_id"),
        Index("ix_episode_media_file_unique_id", "file_unique_id"),
        CheckConstraint("quality > 0", name="ck_media_quality_positive"),
        CheckConstraint("size_bytes > 0", name="ck_media_size_positive"),
    )

    def __repr__(self) -> str:
        return f"<EpisodeMedia(episode_id={self.episode_id!r}, quality={self.quality})>"


class User(TimestampMixin, Base):
    """
    Модель пользователя бота.

    Хранит информацию о пользователях Telegram.
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    geo: Mapped[str | None] = mapped_column(String(8))  # Country code
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )
    banned_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    favorites: Mapped[list[Favorite]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    watch_history: Mapped[list[WatchHistory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_user_username", "username"),
        Index("ix_user_last_seen_at", "last_seen_at"),
        Index("ix_user_is_admin", "is_admin", postgresql_where="is_admin = true"),
    )

    @property
    def is_banned(self) -> bool:
        """Проверяет, забанен ли пользователь."""
        return self.banned_at is not None

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r})>"


class Favorite(Base):
    """
    Модель избранного.

    Связь пользователя и аниме в избранном.
    """

    __tablename__ = "favorite"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    anime_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("anime.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="favorites")
    anime: Mapped[Anime] = relationship()

    __table_args__ = (
        Index("ix_favorite_anime_id", "anime_id"),
        Index("ix_favorite_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Favorite(user_id={self.user_id}, anime_id={self.anime_id!r})>"


class Rating(Base):
    """
    Модель оценки аниме пользователем.
    """

    __tablename__ = "rating"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    anime_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("anime.id", ondelete="CASCADE"),
        primary_key=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="ratings")
    anime: Mapped[Anime] = relationship()

    __table_args__ = (
        Index("ix_rating_anime_id", "anime_id"),
        CheckConstraint("score >= 1 AND score <= 10", name="ck_rating_score_range"),
    )

    def __repr__(self) -> str:
        return f"<Rating(user_id={self.user_id}, anime_id={self.anime_id!r}, score={self.score})>"


class WatchHistory(Base):
    """
    История просмотра эпизодов.

    Отслеживает прогресс просмотра пользователя.
    """

    __tablename__ = "watch_history"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    episode_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("episode.id", ondelete="CASCADE"),
        primary_key=True,
    )
    watched_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
    )
    progress_seconds: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user: Mapped[User] = relationship(back_populates="watch_history")
    episode: Mapped[Episode] = relationship()

    __table_args__ = (
        Index("ix_watch_history_episode_id", "episode_id"),
        Index("ix_watch_history_watched_at", "watched_at"),
        CheckConstraint("progress_seconds >= 0", name="ck_watch_progress_positive"),
    )

    def __repr__(self) -> str:
        return f"<WatchHistory(user_id={self.user_id}, episode_id={self.episode_id!r})>"
