"""Model de sugestões de mapas feitas por jogadores logados (map_suggestions)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import MapSuggestionStatus, enum_column


class MapSuggestion(Base):
    __tablename__ = "map_suggestions"
    __table_args__ = (Index("ix_map_suggestions_ss_id_status", "ss_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ss_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # jogador que sugeriu
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    beatsaver_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    song_author: Mapped[str | None] = mapped_column(String(128))
    mapper: Mapped[str | None] = mapped_column(String(128))
    bpm: Mapped[float | None] = mapped_column(Float)
    cover_url: Mapped[str | None] = mapped_column(String(512))
    note: Mapped[str | None] = mapped_column(String(280))
    status: Mapped[MapSuggestionStatus] = mapped_column(
        enum_column(MapSuggestionStatus),
        nullable=False,
        default=MapSuggestionStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(64))  # id do staff que revisou

    def __repr__(self) -> str:
        return f"<MapSuggestion id={self.id} hash={self.hash!r} status={self.status}>"
