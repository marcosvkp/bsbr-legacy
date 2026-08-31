"""add webhook_configs (webhooks Discord configuráveis pelo admin)

Revision ID: b5c6d7e8f9a0
Revises: a1b2c3d4e5f6
Create Date: 2026-08-31

Webhooks de notificação (reweight de mapas) gerenciados pela aba admin.
Quando a tabela está vazia, o backend usa DISCORD_WEBHOOK_URL (multi por
vírgula) como fallback.
"""

import sqlalchemy as sa

from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )


def downgrade() -> None:
    op.drop_table("webhook_configs")
