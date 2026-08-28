"""Model de usuários staff (staff_users)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StaffUser(Base):
    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="staff")

    def __repr__(self) -> str:
        return f"<StaffUser id={self.id} discord_id={self.discord_id!r} role={self.role!r}>"
