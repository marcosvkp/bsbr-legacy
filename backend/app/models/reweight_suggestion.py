"""Model de sugestões de reweight (reweight_suggestions)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import SuggestionStatus, enum_column


class ReweightSuggestion(Base):
    __tablename__ = "reweight_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("difficulties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observed_acc: Mapped[float | None] = mapped_column(Float)
    expected_acc: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    delta_stars: Mapped[float | None] = mapped_column(Float)
    # Nível textual do algoritmo: none | low | medium | high
    confidence: Mapped[str | None] = mapped_column(String(8))
    suggested_stars: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[SuggestionStatus] = mapped_column(
        enum_column(SuggestionStatus), nullable=False, default=SuggestionStatus.PENDING, index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(64))  # ss_id / discord_id do staff
    # "collect" = gerada pelo batch semanal; "manual" = enfileirada no catálogo do admin
    origin: Mapped[str] = mapped_column(String(8), nullable=False, default="collect")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    difficulty: Mapped["Difficulty"] = relationship(back_populates="reweight_suggestions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ReweightSuggestion id={self.id} difficulty_id={self.difficulty_id} status={self.status}>"
