"""Model do dataset de referência de estrelas (star_reference).

Coletado manualmente pelo CLI `build_star_dataset` (ScoreSaber + BeatLeader):
lista de mapas/dificuldades rankeados + amostra estratificada de acc por
banda de estrelas. Alimenta a curva empírica expected-acc × estrelas e o
pool de doadores do remap. Nunca alimenta scores/players/ranking.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StarReference(Base):
    __tablename__ = "star_reference"
    __table_args__ = (UniqueConstraint("source", "leaderboard_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    leaderboard_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hash: Mapped[str | None] = mapped_column(String(64), index=True)
    song_name: Mapped[str | None] = mapped_column(String(256))
    difficulty_name: Mapped[str | None] = mapped_column(String(64))
    stars: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    total_scores: Mapped[int | None] = mapped_column(Integer)
    max_score: Mapped[int | None] = mapped_column(Integer)
    median_top_acc: Mapped[float | None] = mapped_column(Float)
    sample_n: Mapped[int | None] = mapped_column(Integer)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<StarReference {self.source}:{self.leaderboard_id} stars={self.stars}>"
