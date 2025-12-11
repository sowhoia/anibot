"""Add indexes for search and lookups"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_anime_title", "anime", ["title"])
    op.create_index("ix_anime_title_orig", "anime", ["title_orig"])
    op.create_index("ix_anime_year", "anime", ["year"])

    op.create_index(
        "ix_anime_translation_translation_id",
        "anime_translation",
        ["translation_id"],
    )

    op.create_index(
        "ix_episode_anime_translation",
        "episode",
        ["anime_id", "translation_id"],
    )
    op.create_index(
        "ix_episode_translation_number",
        "episode",
        ["translation_id", "number"],
    )


def downgrade() -> None:
    op.drop_index("ix_episode_translation_number", table_name="episode")
    op.drop_index("ix_episode_anime_translation", table_name="episode")
    op.drop_index("ix_anime_translation_translation_id", table_name="anime_translation")
    op.drop_index("ix_anime_year", table_name="anime")
    op.drop_index("ix_anime_title_orig", table_name="anime")
    op.drop_index("ix_anime_title", table_name="anime")

