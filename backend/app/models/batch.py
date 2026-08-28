"""Model de batches de recálculo (batches)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base
from app.models.enums import BatchKind, enum_column


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[BatchKind] = mapped_column(
        enum_column(BatchKind), nullable=False, default=BatchKind.MANUAL, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # JSONB-like portável

    rating_history: Mapped[list["RatingHistory"]] = relationship(back_populates="batch")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Batch id={self.id} kind={self.kind}>"
