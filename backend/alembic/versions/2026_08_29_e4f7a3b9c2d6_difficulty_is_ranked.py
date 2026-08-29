"""add difficulty.is_ranked

Revision ID: e4f7a3b9c2d6
Revises: d9e6b2c4a1f0
Create Date: 2026-08-29

Staff pode excluir dificuldades inviáveis de um mapa rankeado. Dificuldades
com is_ranked=false não contam para ranking, reweight, playlists nem
leaderboards — o mapa permanece RANKED.
"""

import sqlalchemy as sa

from alembic import op

revision = "e4f7a3b9c2d6"
down_revision = "d9e6b2c4a1f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("difficulties") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_ranked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("difficulties") as batch_op:
        batch_op.drop_column("is_ranked")
