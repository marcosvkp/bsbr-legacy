"""Notificação Discord via webhook — reweight de mapas.

Os endpoints (URLs) são configuráveis pelo admin (tabela ``webhook_configs``)
e podem ser vários. Quando nenhum está cadastrado, usa ``DISCORD_WEBHOOK_URL``
do ambiente (aceita vários URLs separados por vírgula) como fallback.

NOTA: esse endpoint é apenas para notificações de REWEIGHT de mapas — o
relatório de sync/batch NÃO vai para cá (a integração não recebe payload de
batch; só o resumo dos mapas reweightados, estilo "Monthly Reweight").
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import WebhookConfig

REWEIGHT_COLOR = 0xF5C542  # dourado (ícones de estrela do site)
MAX_EMBED_DESC = 4096  # limite do Discord para description
MAX_ROWS_IN_DESC = 30  # se passar, envia por campos em blocos


async def get_webhook_urls(db: AsyncSession) -> list[str]:
    """URLs habilitadas da tabela; sem registros, fallback do ambiente."""
    rows = (
        await db.scalars(
            select(WebhookConfig).where(WebhookConfig.enabled.is_(True)).order_by(WebhookConfig.id)
        )
    ).all()
    if rows:
        return [r.url for r in rows]
    env = get_settings().discord_webhook_url
    if env:
        return [u.strip() for u in env.split(",") if u.strip()]
    return []


def _format_row(r: dict[str, Any]) -> str:
    before = r.get("before")
    after = r.get("after")
    arrow = "→"
    before_str = f"{before:.2f}" if before is not None else "—"
    after_str = f"{after:.2f}" if after is not None else "—"
    return (
        f"**{r.get('map_name', '?')}** "
        f"(`{r.get('difficulty', '?')}`) "
        f"por *{r.get('mapper', '?')}* — "
        f":star: {before_str} {arrow} :star: {after_str}"
    )


def _build_embed(rows: list[dict[str, Any]], title: str | None = None) -> dict[str, Any]:
    """Embed estilo 'Monthly Reweight': título com data + 1 linha por mapa."""
    lines = [_format_row(r) for r in rows]
    return {
        "title": title or "Reweight de mapas",
        "description": "\n".join(lines)[:MAX_EMBED_DESC],
        "color": REWEIGHT_COLOR,
        "footer": {"text": f"{len(rows)} dificuldades reweightadas"},
    }


async def send_reweight_report(
    db: AsyncSession,
    rows: list[dict[str, Any]],
    title: str | None = None,
) -> int:
    """Envia o relatório de reweight para TODOS os webhooks configurados.

    Retorna quantos webhooks receberam (200/204). Nunca levanta — falha de
    notificação não pode derrubar o batch nem a ação do admin.
    """
    if not rows:
        return 0
    urls = await get_webhook_urls(db)
    if not urls:
        return 0

    embeds = [_build_embed(rows, title)]
    payload = {"embeds": embeds}

    sent = 0
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for url in urls:
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in (200, 204):
                        sent += 1
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        pass
    return sent
