"""widen beatsaver_id to 64 chars

Revision ID: d9e6b2c4a1f0
Revises: c8f5e2a7b1d4
Create Date: 2026-08-28

O qualify aceita hash SHA1 (40 chars) como source e grava em beatsaver_id,
que era varchar(32) — estourava com StringDataRightTruncationError.
"""

import sqlalchemy as sa

from alembic import op

revision = "d9e6b2c4a1f0"
down_revision = "c8f5e2a7b1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("maps") as batch_op:
        batch_op.alter_column("beatsaver_id", type_=sa.String(64), existing_type=sa.String(32))


def downgrade() -> None:
    with op.batch_alter_table("maps") as batch_op:
        batch_op.alter_column("beatsaver_id", type_=sa.String(32), existing_type=sa.String(64))