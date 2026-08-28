"""Model de scores por jogador/dificuldade (scores)."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "difficulty_id", "time_set", name="uq_scores_player_difficulty_time_set"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("difficulties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    acc: Mapped[float | None] = mapped_column(Float)
    modifiers: Mapped[str | None] = mapped_column(String(64))  # ex. "NF", "DA"…
    full_combo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pp: Mapped[float | None] = mapped_column(Float)
    pp_acc: Mapped[float | None] = mapped_column(Float)
    pp_tech: Mapped[float | None] = mapped_column(Float)
    pp_speed: Mapped[float | None] = mapped_column(Float)
    # PP do jogador no ScoreSaber no momento do score (filtro de casuais do reweight)
    ss_player_pp: Mapped[float | None] = mapped_column(Float)
    leaderboard_rank: Mapped[int | None] = mapped_column(Integer)
    time_set: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    player: Mapped["Player"] = relationship(back_populates="scores")  # noqa: F821
    difficulty: Mapped["Difficulty"] = relationship(back_populates="scores")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Score id={self.id} player_id={self.player_id} pp={self.pp}>"
