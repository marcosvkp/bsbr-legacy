"""GET /stars-bands — faixas de 0.5★ com o melhor score de cada faixa.

Porte do "stars ranking" do legado (`references/bsbr/app/ranking/__init__.py`,
`generate_star_ranking`): para cada faixa de 0.5★ de stars, o score de maior PP
daquela faixa (jogador + mapa), agora agregado no banco com window functions.
`scope=br` filtra scores de jogadores brasileiros; `scope=global` não filtra.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.db import get_db
from app.models import Difficulty, Map, MapStatus, Player, Score

router = APIRouter()

STEP = 0.5


@router.get("/stars-bands")
async def get_stars_bands(
    scope: str = Query("br", pattern="^(br|global)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"stars-bands:{scope}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    band_expr = func.floor(Difficulty.total_stars * (1 / STEP)) / (1 / STEP)
    rank_over_band = func.row_number().over(
        partition_by=band_expr, order_by=(Score.pp.desc(), Score.id)
    )
    count_over_band = func.count().over(partition_by=band_expr)

    query = (
        select(
            band_expr.label("band"),
            count_over_band.label("score_count"),
            Player.ss_id.label("player_ss_id"),
            Player.name.label("player_name"),
            Player.country.label("player_country"),
            Player.avatar_url.label("avatar_url"),
            Map.name.label("map_name"),
            Map.hash.label("map_hash"),
            Map.beatsaver_id.label("beatsaver_id"),
            Difficulty.name.label("difficulty"),
            Difficulty.total_stars.label("stars"),
            Score.acc.label("acc"),
            Score.pp.label("pp"),
            rank_over_band.label("rn"),
        )
        .select_from(Score)
        .join(Difficulty, Score.difficulty_id == Difficulty.id)
        .join(Map, Difficulty.map_id == Map.id)
        .join(Player, Score.player_id == Player.id)
        .where(Map.status == MapStatus.RANKED)
        .where(Difficulty.total_stars.is_not(None))
        .where(Score.pp.is_not(None))
        .where(Score.pp > 0)
    )
    if scope == "br":
        query = query.where(func.upper(Player.country) == "BR")

    rows = (await db.execute(query.order_by(band_expr))).all()

    payload = {
        "scope": scope,
        "step": STEP,
        "bands": [
            {
                "min": row.band,
                "max": row.band + STEP,
                "label": f"{row.band:.2f}–{row.band + STEP:.2f}★",
                "score_count": row.score_count,
                "top": {
                    "player_ss_id": row.player_ss_id,
                    "player_name": row.player_name,
                    "player_country": row.player_country,
                    "avatar_url": row.avatar_url,
                    "map_name": row.map_name,
                    "map_hash": row.map_hash,
                    "beatsaver_id": row.beatsaver_id,
                    "difficulty": row.difficulty,
                    "stars": row.stars,
                    "acc": row.acc,
                    "pp": round(row.pp, 2),
                },
            }
            for row in rows
            if row.rn == 1
        ],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload
