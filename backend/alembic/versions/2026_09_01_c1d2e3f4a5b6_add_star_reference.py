"""add star_reference (dataset de referência de estrelas)

Revision ID: c1d2e3f4a5b6
Revises: b5c6d7e8f9a0
Create Date: 2026-09-01

Dataset coletado manualmente (CLI build_star_dataset): lista de mapas
ranqueados + amostra estratificada de acc por banda, em ScoreSaber e
BeatLeader. Alimenta a curva empírica expected-acc e o pool de doadores
do remap — nunca entra em scores/players/ranking.
"""

import sqlalchemy as sa

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "star_reference",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("leaderboard_id", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=True),
        sa.Column("song_name", sa.String(256), nullable=True),
        sa.Column("difficulty_name", sa.String(64), nullable=True),
        sa.Column("stars", sa.Float(), nullable=False),
        sa.Column("total_scores", sa.Integer(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=True),
        sa.Column("median_top_acc", sa.Float(), nullable=True),
        sa.Column("sample_n", sa.Integer(), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "leaderboard_id"),
    )
    op.create_index("ix_star_reference_source", "star_reference", ["source"])
    op.create_index("ix_star_reference_leaderboard_id", "star_reference", ["leaderboard_id"])
    op.create_index("ix_star_reference_hash", "star_reference", ["hash"])
    op.create_index("ix_star_reference_stars", "star_reference", ["stars"])


def downgrade() -> None:
    op.drop_index("ix_star_reference_stars", table_name="star_reference")
    op.drop_index("ix_star_reference_hash", table_name="star_reference")
    op.drop_index("ix_star_reference_leaderboard_id", table_name="star_reference")
    op.drop_index("ix_star_reference_source", table_name="star_reference")
    op.drop_table("star_reference")
