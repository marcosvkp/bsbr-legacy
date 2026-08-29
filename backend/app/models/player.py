"""Model de jogadores (players)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ss_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Vínculo com a conta BeatLeader do mesmo jogador (resolver BL → SS).
    # Para jogadores Steam (maioria), bl_id == ss_id == Steam ID.
    bl_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    bl_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8), index=True)  # ISO 3166-1 (ex. "BR")
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    hmd: Mapped[str | None] = mapped_column(String(32))  # ex. "quest", "index"
    pp_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pp_acc: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pp_tech: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pp_speed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank: Mapped[int | None] = mapped_column(Integer, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scores: Mapped[list["Score"]] = relationship(  # noqa: F821
        back_populates="player", cascade="all, delete-orphan"
    )
    rank_snapshots: Mapped[list["RankSnapshot"]] = relationship(back_populates="player")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Player id={self.id} ss_id={self.ss_id!r} name={self.name!r}>"
