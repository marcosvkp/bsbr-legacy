"""Endpoints de imagem OpenGraph (1200x630) para share no Discord/WhatsApp.

- GET /og/players/{ss_id}.png  — avatar + nome + PP + ACC/TECH/SPEED
- GET /og/maps/{hash}.png     — cover + nome + mapper + stars
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models import Difficulty, Map, MapStatus, Player
from app.services import og_image

router = APIRouter()

PNG = "image/png"
CACHE = "public, max-age=120"


def _png(data: bytes) -> Response:
    return Response(
        content=data,
        media_type=PNG,
        headers={"Cache-Control": CACHE},
    )


@router.get("/og/players/{ss_id}.png")
async def og_player(ss_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    player = (
        await db.scalars(select(Player).where(Player.ss_id == ss_id))
    ).first()
    if player is None:
        return Response(status_code=404, content=b"not found", media_type="text/plain")
    payload = {
        "kind": "player",
        "name": player.name or player.ss_id,
        "avatar_url": player.avatar_url,
        "country": player.country,
        "rank": player.rank,
        "pp_total": player.pp_total or 0,
        "pp_acc": player.pp_acc or 0,
        "pp_tech": player.pp_tech or 0,
        "pp_speed": player.pp_speed or 0,
    }
    return _png(await _render_async(payload))


@router.get("/og/maps/{map_hash}.png")
async def og_map(map_hash: str, db: AsyncSession = Depends(get_db)) -> Response:
    map_ = (
        await db.scalars(
            select(Map)
            .where(Map.hash == map_hash.lower(), Map.status == MapStatus.RANKED)
        )
    ).first()
    if map_ is None:
        return Response(status_code=404, content=b"not found", media_type="text/plain")
    top = (
        await db.scalars(
            select(Difficulty)
            .where(
                Difficulty.map_id == map_.id,
                Difficulty.characteristic == "Standard",
                Difficulty.is_ranked.is_(True),
            )
            .order_by(Difficulty.total_stars.desc().nulls_last())
            .limit(1)
        )
    ).first()
    payload = {
        "kind": "map",
        "name": map_.name or "Mapa",
        "mapper": map_.mapper or "",
        "cover_url": map_.cover_url,
        "total_stars": float(top.total_stars) if top and top.total_stars else None,
        "bpm": float(map_.bpm) if map_.bpm else None,
    }
    return _png(await _render_async(payload))


async def _render_async(payload: dict) -> bytes:
    import asyncio

    return await asyncio.to_thread(og_image.render, payload)
