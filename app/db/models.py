from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    ForeignKey,
    Boolean,
    Float,
    UniqueConstraint,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Anime(Base):
    __tablename__ = "anime"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    title_orig = Column(String)
    alt_titles = Column(JSON, default=list)
    year = Column(Integer)
    poster_url = Column(String)
    description = Column(String)
    genres = Column(JSON, default=list)
    rating_shiki = Column(Float)
    rating_kinopoisk = Column(Float)
    rating_imdb = Column(Float)
    episodes_total = Column(Integer)
    external_ids = Column(JSON, default=dict)
    blocked_countries = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    translations = relationship("AnimeTranslation", back_populates="anime")
    episodes = relationship("Episode", back_populates="anime")
    __table_args__ = (
        Index("ix_anime_title", "title"),
        Index("ix_anime_title_orig", "title_orig"),
        Index("ix_anime_year", "year"),
    )


class Translation(Base):
    __tablename__ = "translation"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    type = Column(String)

    anime_links = relationship("AnimeTranslation", back_populates="translation")


class AnimeTranslation(Base):
    __tablename__ = "anime_translation"
    anime_id = Column(String, ForeignKey("anime.id"), primary_key=True)
    translation_id = Column(Integer, ForeignKey("translation.id"), primary_key=True)
    episodes_available = Column(Integer, default=0)
    last_episode = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    anime = relationship("Anime", back_populates="translations")
    translation = relationship("Translation", back_populates="anime_links")
    __table_args__ = (
        Index("ix_anime_translation_translation_id", "translation_id"),
    )


class Episode(Base):
    __tablename__ = "episode"
    id = Column(String, primary_key=True)
    anime_id = Column(String, ForeignKey("anime.id"))
    translation_id = Column(Integer, ForeignKey("translation.id"))
    number = Column(Integer, nullable=False)
    season = Column(Integer, default=1)
    title = Column(String)
    duration = Column(Integer)
    preview_image = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    anime = relationship("Anime", back_populates="episodes")
    translation = relationship("Translation")
    media = relationship("EpisodeMedia", back_populates="episode", uselist=False)

    __table_args__ = (
        UniqueConstraint("anime_id", "translation_id", "number", name="uq_episode_number"),
        Index("ix_episode_anime_translation", "anime_id", "translation_id"),
        Index("ix_episode_translation_number", "translation_id", "number"),
    )


class EpisodeMedia(Base):
    __tablename__ = "episode_media"
    episode_id = Column(String, ForeignKey("episode.id"), primary_key=True)
    telegram_chat_id = Column(String, nullable=False)
    telegram_message_id = Column(Integer, nullable=False)
    file_unique_id = Column(String)
    quality = Column(Integer)
    source_url = Column(String)
    checksum = Column(String)
    size_bytes = Column(Integer)

    episode = relationship("Episode", back_populates="media")


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    language_code = Column(String)
    is_premium = Column(Boolean, default=False)
    geo = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    banned_at = Column(DateTime)
    is_admin = Column(Boolean, default=False)

    favorites = relationship("Favorite", back_populates="user")
    ratings = relationship("Rating", back_populates="user")


class Favorite(Base):
    __tablename__ = "favorite"
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    anime_id = Column(String, ForeignKey("anime.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="favorites")
    anime = relationship("Anime")


class Rating(Base):
    __tablename__ = "rating"
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    anime_id = Column(String, ForeignKey("anime.id"), primary_key=True)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="ratings")
    anime = relationship("Anime")

