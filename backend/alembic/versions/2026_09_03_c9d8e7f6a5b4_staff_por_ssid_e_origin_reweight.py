"""staff por ss_id (Steam) + origin na reweight_suggestions

Revision ID: c9d8e7f6a5b4
Revises: b5c6d7e8f9a0
Create Date: 2026-09-03

- staff_users: identidade passa de discord_id para ss_id (Steam ID /
  ScoreSaber), com name e created_by. O painel admin é liberado validando
  o cookie bsbr_user_session contra esta tabela.
- reweight_suggestions: coluna origin ('collect' do batch | 'manual' da
  fila do admin).
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d8e7f6a5b4"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- staff_users: recria chaveada por ss_id ---
    op.drop_index(op.f("ix_staff_users_discord_id"), table_name="staff_users")
    op.drop_table("staff_users")

    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ss_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
    )
    with op.batch_alter_table("staff_users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_staff_users_ss_id"), ["ss_id"], unique=True)

    # Owner padrão (Marcos / admin do BSBR).
    op.execute(
        "INSERT INTO staff_users (ss_id, role, name, created_by) "
        "VALUES ('76561198275522989', 'owner', 'Marcos', 'system')"
    )

    # --- reweight_suggestions: origin ---
    op.add_column(
        "reweight_suggestions",
        sa.Column(
            "origin",
            sa.String(length=8),
            nullable=False,
            server_default="collect",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("reweight_suggestions", schema=None) as batch_op:
        batch_op.drop_column("origin")

    op.drop_index(op.f("ix_staff_users_ss_id"), table_name="staff_users")
    op.drop_table("staff_users")

    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discord_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
    )
    with op.batch_alter_table("staff_users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_staff_users_discord_id"), ["discord_id"], unique=True)
