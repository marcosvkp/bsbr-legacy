"""Model de dificuldades analisadas (difficulties)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base


class Difficulty(Base):
    __tablename__ = "difficulties"
    __table_args__ = (
        UniqueConstraint("map_id", "characteristic", "name", name="uq_difficulties_map_char_name"),
        Index("ix_difficulties_total_stars", "total_stars"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_id: Mapped[int] = mapped_column(
        ForeignKey("maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    characteristic: Mapped[str] = mapped_column(String(16), nullable=False)  # Standard, 90Degree…
    name: Mapped[str] = mapped_column(String(32), nullable=False)  # Expert+, Hard…
    njs: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[int | None] = mapped_column(Integer)
    max_pp: Mapped[float | None] = mapped_column(Float)
    total_stars: Mapped[float | None] = mapped_column(Float)
    acc_stars: Mapped[float | None] = mapped_column(Float)
    tech_stars: Mapped[float | None] = mapped_column(Float)
    speed_stars: Mapped[float | None] = mapped_column(Float)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # JSONB-like portável
    style_tags: Mapped[list[Any] | None] = mapped_column(JSON)
    model_version: Mapped[str | None] = mapped_column(String(32))
    # Leaderboard correspondente no ScoreSaber (fonte dos scores)
    ss_leaderboard_id: Mapped[str | None] = mapped_column(String(32), index=True)
    ranked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_ranked: Mapped[bool] = mapped_column(default=True)

    map: Mapped["Map"] = relationship(back_populates="difficulties")  # noqa: F821
    scores: Mapped[list["Score"]] = relationship(  # noqa: F821
        back_populates="difficulty", cascade="all, delete-orphan"
    )
    rating_history: Mapped[list["RatingHistory"]] = relationship(  # noqa: F821
        back_populates="difficulty", cascade="all, delete-orphan"
    )
    reweight_suggestions: Mapped[list["ReweightSuggestion"]] = relationship(  # noqa: F821
        back_populates="difficulty", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Difficulty id={self.id} map_id={self.map_id} name={self.name!r}>"
