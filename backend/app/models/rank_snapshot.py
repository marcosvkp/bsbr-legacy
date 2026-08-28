"""Model de snapshots semanais de ranking (rank_snapshots)."""

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class RankSnapshot(Base):
    __tablename__ = "rank_snapshots"
    __table_args__ = (
        UniqueConstraint("week", "player_id", name="uq_rank_snapshots_week_player"),
        Index("ix_rank_snapshots_week_rank", "week", "rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO, ex. "2026-W34"
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    pp_total: Mapped[float | None] = mapped_column(Float)
    pp_acc: Mapped[float | None] = mapped_column(Float)
    pp_tech: Mapped[float | None] = mapped_column(Float)
    pp_speed: Mapped[float | None] = mapped_column(Float)

    player: Mapped["Player"] = relationship(back_populates="rank_snapshots")  # noqa: F821

    def __repr__(self) -> str:
        return f"<RankSnapshot id={self.id} week={self.week!r} player_id={self.player_id} rank={self.rank}>"
