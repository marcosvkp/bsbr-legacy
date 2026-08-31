"""add map_suggestions (sugestão de mapas por jogadores logados)

Revision ID: a1b2c3d4e5f6
Revises: f8b5c2a7d3e1
Create Date: 2026-08-31

Sugestões de mapas feitas por jogadores do site (login Steam): limite de 3
pendentes por jogador; ``approved`` vira um Map candidate sem ML e
``rejected`` libera o slot.
"""

import sqlalchemy as sa

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f8b5c2a7d3e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ss_id", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("beatsaver_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("song_author", sa.String(128), nullable=True),
        sa.Column("mapper", sa.String(128), nullable=True),
        sa.Column("bpm", sa.Float(), nullable=True),
        sa.Column("cover_url", sa.String(512), nullable=True),
        sa.Column("note", sa.String(280), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="mapsuggestionstatus", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_map_suggestions_ss_id", "map_suggestions", ["ss_id"])
    op.create_index("ix_map_suggestions_hash", "map_suggestions", ["hash"])
    op.create_index("ix_map_suggestions_beatsaver_id", "map_suggestions", ["beatsaver_id"])
    op.create_index("ix_map_suggestions_status", "map_suggestions", ["status"])
    op.create_index("ix_map_suggestions_ss_id_status", "map_suggestions", ["ss_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_map_suggestions_ss_id_status", table_name="map_suggestions")
    op.drop_index("ix_map_suggestions_status", table_name="map_suggestions")
    op.drop_index("ix_map_suggestions_beatsaver_id", table_name="map_suggestions")
    op.drop_index("ix_map_suggestions_hash", table_name="map_suggestions")
    op.drop_index("ix_map_suggestions_ss_id", table_name="map_suggestions")
    op.drop_table("map_suggestions")
