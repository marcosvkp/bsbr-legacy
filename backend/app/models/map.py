"""Model de mapas rankeados (maps)."""

from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, Float, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import MapStatus, enum_column


class Map(Base):
    __tablename__ = "maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    beatsaver_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    song_author: Mapped[str | None] = mapped_column(String(128))
    mapper: Mapped[str | None] = mapped_column(String(128))
    bpm: Mapped[float | None] = mapped_column(Float)
    cover_url: Mapped[str | None] = mapped_column(String(512))
    tags: Mapped[list[Any] | None] = mapped_column(JSON)
    status: Mapped[MapStatus] = mapped_column(
        enum_column(MapStatus), nullable=False, default=MapStatus.CANDIDATE, index=True
    )
    submitted_by: Mapped[str | None] = mapped_column(String(64))  # ss_id do submetedor
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    difficulties: Mapped[list["Difficulty"]] = relationship(  # noqa: F821
        back_populates="map", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Map id={self.id} hash={self.hash!r} name={self.name!r} status={self.status}>"
