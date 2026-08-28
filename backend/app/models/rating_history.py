"""Model de auditoria de ratings (rating_history)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("difficulties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_stars_before: Mapped[float | None] = mapped_column(Float)
    total_stars_after: Mapped[float | None] = mapped_column(Float)
    acc_stars_before: Mapped[float | None] = mapped_column(Float)
    acc_stars_after: Mapped[float | None] = mapped_column(Float)
    tech_stars_before: Mapped[float | None] = mapped_column(Float)
    tech_stars_after: Mapped[float | None] = mapped_column(Float)
    speed_stars_before: Mapped[float | None] = mapped_column(Float)
    speed_stars_after: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="SET NULL"), index=True
    )
    applied_by: Mapped[str | None] = mapped_column(String(64))  # discord_id do staff
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    difficulty: Mapped["Difficulty"] = relationship(back_populates="rating_history")  # noqa: F821
    batch: Mapped["Batch | None"] = relationship(back_populates="rating_history")  # noqa: F821

    def __repr__(self) -> str:
        return f"<RatingHistory id={self.id} difficulty_id={self.difficulty_id} reason={self.reason!r}>"
