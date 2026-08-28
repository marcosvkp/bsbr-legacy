"""Notificação Discord via webhook (relatório do batch semanal)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


async def send_batch_report(payload: dict[str, Any]) -> bool:
    """Envia embed para o webhook configurado. Silencioso se não configurado.

    Retorna True quando entregue; False caso contrário (nunca levanta —
    falha de notificação não pode derrubar o batch).
    """
    url = get_settings().discord_webhook_url
    if not url:
        return False
    body = {
        "embeds": [
            {
                "title": payload.get("title", "BSBR"),
                "description": payload.get("description"),
                "color": 0xE3354B,  # vermelho Beat Saber
                "fields": [
                    {"name": name, "value": str(value)[:1024] or "—", "inline": len(str(value)) < 40}
                    for name, value in payload.get("fields", {}).items()
                ],
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            return resp.status_code in (200, 204)
    except httpx.HTTPError:
        return False
