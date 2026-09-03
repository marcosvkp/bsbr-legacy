"""Model de usuários staff (staff_users).

Identidade por ``ss_id`` (Steam ID / ScoreSaber) — o painel admin é
liberado validando o cookie ``bsbr_user_session`` contra esta tabela.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StaffUser(Base):
    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    ss_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="staff")
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<StaffUser id={self.id} ss_id={self.ss_id!r} role={self.role!r}>"
