"""add ss_leaderboard_id to difficulties

Revision ID: b7e4d1c9a2f3
Revises: dee37a9cc58e
Create Date: 2026-08-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7e4d1c9a2f3'
down_revision: str | None = 'dee37a9cc58e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('difficulties', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ss_leaderboard_id', sa.String(length=32), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_difficulties_ss_leaderboard_id'), ['ss_leaderboard_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('difficulties', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_difficulties_ss_leaderboard_id'))
        batch_op.drop_column('ss_leaderboard_id')
