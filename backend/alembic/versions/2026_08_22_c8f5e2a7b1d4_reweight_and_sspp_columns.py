"""reweight and sspp columns

Revision ID: c8f5e2a7b1d4
Revises: b7e4d1c9a2f3
Create Date: 2026-08-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8f5e2a7b1d4'
down_revision: str | None = 'b7e4d1c9a2f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PP do jogador no ScoreSaber no momento do score (filtro de casuais do reweight)
    with op.batch_alter_table('scores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ss_player_pp', sa.Float(), nullable=True))

    with op.batch_alter_table('reweight_suggestions', schema=None) as batch_op:
        batch_op.alter_column(
            'confidence',
            existing_type=sa.Float(),
            type_=sa.String(length=8),
            existing_nullable=True,
            postgresql_using='confidence::text',
        )
        batch_op.add_column(sa.Column('suggested_stars', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('reason', sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reweight_suggestions', schema=None) as batch_op:
        batch_op.drop_column('reason')
        batch_op.drop_column('suggested_stars')
        batch_op.alter_column(
            'confidence',
            existing_type=sa.String(length=8),
            type_=sa.Float(),
            existing_nullable=True,
            postgresql_using='NULL',
        )

    with op.batch_alter_table('scores', schema=None) as batch_op:
        batch_op.drop_column('ss_player_pp')
