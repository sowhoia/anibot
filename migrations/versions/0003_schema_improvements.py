"""Schema improvements: new fields, indexes, constraints, watch_history table.

Revision ID: 0003_schema_improvements
Revises: 0002_add_indexes
Create Date: 2024-01-15

Changes:
- Add status column to anime
- Add created_at to episode_media
- Add watch_history table
- Add CASCADE on foreign keys
- Add CHECK constraints
- Add GIN indexes for JSONB columns
- Add partial indexes
- Add additional B-tree indexes for common queries
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0003_schema_improvements"
down_revision = "0002_add_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === Новые колонки ===

    # Добавляем статус аниме
    op.add_column(
        "anime",
        sa.Column("status", sa.String(32), nullable=True),
    )

    # Добавляем created_at для episode_media
    op.add_column(
        "episode_media",
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )

    # === Новая таблица watch_history ===

    op.create_table(
        "watch_history",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("episode_id", sa.String(128), sa.ForeignKey("episode.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("watched_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("progress_seconds", sa.Integer(), default=0),
        sa.Column("completed", sa.Boolean(), default=False),
    )

    # === Новые индексы ===

    # Индекс для статуса аниме
    op.create_index("ix_anime_status", "anime", ["status"])

    # Индекс для updated_at (для дельта-синхронизации)
    op.create_index("ix_anime_updated_at", "anime", ["updated_at"])

    # GIN индексы для JSONB полей
    op.execute(
        "CREATE INDEX ix_anime_alt_titles_gin ON anime USING GIN (alt_titles)"
    )
    op.execute(
        "CREATE INDEX ix_anime_genres_gin ON anime USING GIN (genres)"
    )

    # Частичный индекс для аниме с рейтингом
    op.execute(
        "CREATE INDEX ix_anime_year_rating ON anime (year, rating_shiki) "
        "WHERE rating_shiki IS NOT NULL"
    )

    # Индекс для типа озвучки
    op.create_index("ix_translation_type", "translation", ["type"])

    # Индекс для updated_at в anime_translation
    op.create_index(
        "ix_anime_translation_updated_at",
        "anime_translation",
        ["updated_at"],
    )

    # Индекс для updated_at в episode
    op.create_index("ix_episode_updated_at", "episode", ["updated_at"])

    # Индексы для episode_media
    op.create_index(
        "ix_episode_media_chat_message",
        "episode_media",
        ["telegram_chat_id", "telegram_message_id"],
    )
    op.create_index(
        "ix_episode_media_file_unique_id",
        "episode_media",
        ["file_unique_id"],
    )

    # Индексы для user
    op.create_index("ix_user_username", "user", ["username"])
    op.create_index("ix_user_last_seen_at", "user", ["last_seen_at"])
    op.execute(
        "CREATE INDEX ix_user_is_admin ON \"user\" (is_admin) WHERE is_admin = true"
    )

    # Индексы для favorite
    op.create_index("ix_favorite_anime_id", "favorite", ["anime_id"])
    op.create_index("ix_favorite_created_at", "favorite", ["created_at"])

    # Индексы для rating
    op.create_index("ix_rating_anime_id", "rating", ["anime_id"])

    # Индексы для watch_history
    op.create_index("ix_watch_history_episode_id", "watch_history", ["episode_id"])
    op.create_index("ix_watch_history_watched_at", "watch_history", ["watched_at"])

    # === CHECK constraints ===

    op.create_check_constraint(
        "ck_episode_number_positive",
        "episode",
        "number > 0",
    )
    op.create_check_constraint(
        "ck_episode_season_positive",
        "episode",
        "season > 0",
    )
    op.create_check_constraint(
        "ck_media_quality_positive",
        "episode_media",
        "quality > 0 OR quality IS NULL",
    )
    op.create_check_constraint(
        "ck_media_size_positive",
        "episode_media",
        "size_bytes > 0 OR size_bytes IS NULL",
    )
    op.create_check_constraint(
        "ck_rating_score_range",
        "rating",
        "score >= 1 AND score <= 10",
    )
    op.create_check_constraint(
        "ck_watch_progress_positive",
        "watch_history",
        "progress_seconds >= 0",
    )

    # === Обновление FK с CASCADE ===
    # Пересоздаем FK с ON DELETE CASCADE

    # anime_translation
    op.drop_constraint("anime_translation_anime_id_fkey", "anime_translation", type_="foreignkey")
    op.drop_constraint("anime_translation_translation_id_fkey", "anime_translation", type_="foreignkey")
    op.create_foreign_key(
        "anime_translation_anime_id_fkey",
        "anime_translation",
        "anime",
        ["anime_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "anime_translation_translation_id_fkey",
        "anime_translation",
        "translation",
        ["translation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # episode
    op.drop_constraint("episode_anime_id_fkey", "episode", type_="foreignkey")
    op.drop_constraint("episode_translation_id_fkey", "episode", type_="foreignkey")
    op.create_foreign_key(
        "episode_anime_id_fkey",
        "episode",
        "anime",
        ["anime_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "episode_translation_id_fkey",
        "episode",
        "translation",
        ["translation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # episode_media
    op.drop_constraint("episode_media_episode_id_fkey", "episode_media", type_="foreignkey")
    op.create_foreign_key(
        "episode_media_episode_id_fkey",
        "episode_media",
        "episode",
        ["episode_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # favorite
    op.drop_constraint("favorite_user_id_fkey", "favorite", type_="foreignkey")
    op.drop_constraint("favorite_anime_id_fkey", "favorite", type_="foreignkey")
    op.create_foreign_key(
        "favorite_user_id_fkey",
        "favorite",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "favorite_anime_id_fkey",
        "favorite",
        "anime",
        ["anime_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # rating
    op.drop_constraint("rating_user_id_fkey", "rating", type_="foreignkey")
    op.drop_constraint("rating_anime_id_fkey", "rating", type_="foreignkey")
    op.create_foreign_key(
        "rating_user_id_fkey",
        "rating",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "rating_anime_id_fkey",
        "rating",
        "anime",
        ["anime_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # === Восстановление FK без CASCADE ===

    # rating
    op.drop_constraint("rating_anime_id_fkey", "rating", type_="foreignkey")
    op.drop_constraint("rating_user_id_fkey", "rating", type_="foreignkey")
    op.create_foreign_key(
        "rating_anime_id_fkey",
        "rating",
        "anime",
        ["anime_id"],
        ["id"],
    )
    op.create_foreign_key(
        "rating_user_id_fkey",
        "rating",
        "user",
        ["user_id"],
        ["id"],
    )

    # favorite
    op.drop_constraint("favorite_anime_id_fkey", "favorite", type_="foreignkey")
    op.drop_constraint("favorite_user_id_fkey", "favorite", type_="foreignkey")
    op.create_foreign_key(
        "favorite_anime_id_fkey",
        "favorite",
        "anime",
        ["anime_id"],
        ["id"],
    )
    op.create_foreign_key(
        "favorite_user_id_fkey",
        "favorite",
        "user",
        ["user_id"],
        ["id"],
    )

    # episode_media
    op.drop_constraint("episode_media_episode_id_fkey", "episode_media", type_="foreignkey")
    op.create_foreign_key(
        "episode_media_episode_id_fkey",
        "episode_media",
        "episode",
        ["episode_id"],
        ["id"],
    )

    # episode
    op.drop_constraint("episode_translation_id_fkey", "episode", type_="foreignkey")
    op.drop_constraint("episode_anime_id_fkey", "episode", type_="foreignkey")
    op.create_foreign_key(
        "episode_translation_id_fkey",
        "episode",
        "translation",
        ["translation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "episode_anime_id_fkey",
        "episode",
        "anime",
        ["anime_id"],
        ["id"],
    )

    # anime_translation
    op.drop_constraint("anime_translation_translation_id_fkey", "anime_translation", type_="foreignkey")
    op.drop_constraint("anime_translation_anime_id_fkey", "anime_translation", type_="foreignkey")
    op.create_foreign_key(
        "anime_translation_translation_id_fkey",
        "anime_translation",
        "translation",
        ["translation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "anime_translation_anime_id_fkey",
        "anime_translation",
        "anime",
        ["anime_id"],
        ["id"],
    )

    # === Удаление CHECK constraints ===

    op.drop_constraint("ck_watch_progress_positive", "watch_history", type_="check")
    op.drop_constraint("ck_rating_score_range", "rating", type_="check")
    op.drop_constraint("ck_media_size_positive", "episode_media", type_="check")
    op.drop_constraint("ck_media_quality_positive", "episode_media", type_="check")
    op.drop_constraint("ck_episode_season_positive", "episode", type_="check")
    op.drop_constraint("ck_episode_number_positive", "episode", type_="check")

    # === Удаление индексов ===

    op.drop_index("ix_watch_history_watched_at", table_name="watch_history")
    op.drop_index("ix_watch_history_episode_id", table_name="watch_history")
    op.drop_index("ix_rating_anime_id", table_name="rating")
    op.drop_index("ix_favorite_created_at", table_name="favorite")
    op.drop_index("ix_favorite_anime_id", table_name="favorite")
    op.drop_index("ix_user_is_admin", table_name="user")
    op.drop_index("ix_user_last_seen_at", table_name="user")
    op.drop_index("ix_user_username", table_name="user")
    op.drop_index("ix_episode_media_file_unique_id", table_name="episode_media")
    op.drop_index("ix_episode_media_chat_message", table_name="episode_media")
    op.drop_index("ix_episode_updated_at", table_name="episode")
    op.drop_index("ix_anime_translation_updated_at", table_name="anime_translation")
    op.drop_index("ix_translation_type", table_name="translation")
    op.drop_index("ix_anime_year_rating", table_name="anime")
    op.drop_index("ix_anime_genres_gin", table_name="anime")
    op.drop_index("ix_anime_alt_titles_gin", table_name="anime")
    op.drop_index("ix_anime_updated_at", table_name="anime")
    op.drop_index("ix_anime_status", table_name="anime")

    # === Удаление таблицы ===

    op.drop_table("watch_history")

    # === Удаление колонок ===

    op.drop_column("episode_media", "created_at")
    op.drop_column("anime", "status")
