"""add beatleader links (players.bl_id, difficulties.bl_leaderboard_id)

Revision ID: f8b5c2a7d3e1
Revises: e4f7a3b9c2d6
Create Date: 2026-08-29

Resolver de contas BeatLeader → ScoreSaber:
- players.bl_id: id do jogador no BeatLeader (para Steam, bl_id == ss_id)
- players.bl_resolved_at: quando o vínculo foi (re)confirmado
- difficulties.bl_leaderboard_id: leaderboard do BeatLeader da dificuldade
  (usado pelo sync batch e pelo score ao vivo do BeatLeader)
"""

import sqlalchemy as sa

from alembic import op

revision = "f8b5c2a7d3e1"
down_revision = "e4f7a3b9c2d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.add_column(sa.Column("bl_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("bl_resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_players_bl_id", ["bl_id"], unique=True)
    with op.batch_alter_table("difficulties") as batch_op:
        batch_op.add_column(sa.Column("bl_leaderboard_id", sa.String(64), nullable=True))
        batch_op.create_index("ix_difficulties_bl_leaderboard_id", ["bl_leaderboard_id"])


def downgrade() -> None:
    with op.batch_alter_table("difficulties") as batch_op:
        batch_op.drop_index("ix_difficulties_bl_leaderboard_id")
        batch_op.drop_column("bl_leaderboard_id")
    with op.batch_alter_table("players") as batch_op:
        batch_op.drop_index("ix_players_bl_id")
        batch_op.drop_column("bl_resolved_at")
        batch_op.drop_column("bl_id")
