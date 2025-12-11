"""Initial schema"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anime",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("title_orig", sa.String()),
        sa.Column("alt_titles", sa.JSON(), default=list),
        sa.Column("year", sa.Integer()),
        sa.Column("poster_url", sa.String()),
        sa.Column("description", sa.String()),
        sa.Column("genres", sa.JSON(), default=list),
        sa.Column("rating_shiki", sa.Float()),
        sa.Column("rating_kinopoisk", sa.Float()),
        sa.Column("rating_imdb", sa.Float()),
        sa.Column("episodes_total", sa.Integer()),
        sa.Column("external_ids", sa.JSON(), default=dict),
        sa.Column("blocked_countries", sa.JSON(), default=list),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "translation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("type", sa.String()),
    )

    op.create_table(
        "anime_translation",
        sa.Column("anime_id", sa.String(), sa.ForeignKey("anime.id"), primary_key=True),
        sa.Column("translation_id", sa.Integer(), sa.ForeignKey("translation.id"), primary_key=True),
        sa.Column("episodes_available", sa.Integer(), default=0),
        sa.Column("last_episode", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "episode",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("anime_id", sa.String(), sa.ForeignKey("anime.id")),
        sa.Column("translation_id", sa.Integer(), sa.ForeignKey("translation.id")),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), default=1),
        sa.Column("title", sa.String()),
        sa.Column("duration", sa.Integer()),
        sa.Column("preview_image", sa.String()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("anime_id", "translation_id", "number", name="uq_episode_number"),
    )

    op.create_table(
        "episode_media",
        sa.Column("episode_id", sa.String(), sa.ForeignKey("episode.id"), primary_key=True),
        sa.Column("telegram_chat_id", sa.String(), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("file_unique_id", sa.String()),
        sa.Column("quality", sa.Integer()),
        sa.Column("source_url", sa.String()),
        sa.Column("checksum", sa.String()),
        sa.Column("size_bytes", sa.Integer()),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String()),
        sa.Column("first_name", sa.String()),
        sa.Column("last_name", sa.String()),
        sa.Column("language_code", sa.String()),
        sa.Column("is_premium", sa.Boolean(), default=False),
        sa.Column("geo", sa.String()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("banned_at", sa.DateTime()),
        sa.Column("is_admin", sa.Boolean(), default=False),
    )

    op.create_table(
        "favorite",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("anime_id", sa.String(), sa.ForeignKey("anime.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "rating",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("anime_id", sa.String(), sa.ForeignKey("anime.id"), primary_key=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("rating")
    op.drop_table("favorite")
    op.drop_table("user")
    op.drop_table("episode_media")
    op.drop_table("episode")
    op.drop_table("anime_translation")
    op.drop_table("translation")
    op.drop_table("anime")

