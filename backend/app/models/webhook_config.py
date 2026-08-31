"""Model de webhooks do Discord configuráveis pelo admin (webhook_configs).

Fonte de verdade dos endpoints de notificação (reweight de mapas). Quando
nenhum registro existe, o backend usa ``DISCORD_WEBHOOK_URL`` do ambiente
(vários URLs separados por vírgula) como fallback/seed.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<WebhookConfig id={self.id} enabled={self.enabled} label={self.label!r}>"
