"""add reweight_suggestions.sample_source (origem da amostra)

Revision ID: c6d7e8f9a0b1
Revises: c1d2e3f4a5b6
Create Date: 2026-09-01

Registra de onde veio a performance observada da sugestão: scoresaber_global
(leaderboard global), br_local (tabela scores BR) ou remap (pool por faixa de
estrelas). Nullable para não quebrar sugestões históricas.
"""

import sqlalchemy as sa

from alembic import op

revision = "c6d7e8f9a0b1"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reweight_suggestions", sa.Column("sample_source", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("reweight_suggestions", "sample_source")
