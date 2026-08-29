"""GET /players/{ss_id} e /players/{ss_id}/scores."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.db import get_db
from app.models import Difficulty, Map, MapStatus, Player, RankSnapshot, Score
from app.services.ranking import medals_for_player

router = APIRouter()


async def _get_player(db: AsyncSession, ss_id: str) -> Player:
    player = (
        await db.scalars(select(Player).where(Player.ss_id == ss_id).limit(1))
    ).first()
    if player is None:
        raise HTTPException(status_code=404, detail="jogador não encontrado")
    return player


@router.get("/players/{ss_id}")
async def get_player(ss_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    cache_key = f"player:{ss_id}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    player = await _get_player(db, ss_id)
    medals = await medals_for_player(db, player.id)
    snapshots = (
        (
            await db.scalars(
                select(RankSnapshot)
                .where(RankSnapshot.player_id == player.id)
                .order_by(RankSnapshot.week.desc())
                .limit(12)
            )
        )
        .all()
    )

    payload = {
        "ss_id": player.ss_id,
        "name": player.name,
        "country": player.country,
        "avatar_url": player.avatar_url,
        "rank": player.rank,
        "pp_total": round(player.pp_total, 2),
        "pp_acc": round(player.pp_acc, 2),
        "pp_tech": round(player.pp_tech, 2),
        "pp_speed": round(player.pp_speed, 2),
        "medals": medals,
        "history": [
            {
                "week": s.week,
                "rank": s.rank,
                "pp_total": s.pp_total,
                "pp_acc": s.pp_acc,
                "pp_tech": s.pp_tech,
                "pp_speed": s.pp_speed,
            }
            for s in reversed(snapshots)  # cronológico para gráficos
        ],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload


@router.get("/players/{ss_id}/scores")
async def get_player_scores(
    ss_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    player = await _get_player(db, ss_id)
    base = (
        select(Score, Difficulty, Map)
        .join(Difficulty, Score.difficulty_id == Difficulty.id)
        .join(Map, Difficulty.map_id == Map.id)
        .where(
            Score.player_id == player.id,
            Map.status == MapStatus.RANKED,
            Difficulty.is_ranked.is_(True),
        )
        .order_by(Score.pp.desc().nulls_last())
    )
    rows = (
        (
            await db.execute(base.offset((page - 1) * page_size).limit(page_size + 1))
        )
        .all()
    )
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    return {
        "ss_id": player.ss_id,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
        "items": [
            {
                "map_hash": m.hash,
                "map_name": m.name,
                "cover_url": m.cover_url,
                "difficulty": d.name,
                "total_stars": d.total_stars,
                "acc_stars": d.acc_stars,
                "tech_stars": d.tech_stars,
                "speed_stars": d.speed_stars,
                "score": s.score,
                "acc": s.acc,
                "full_combo": s.full_combo,
                "modifiers": s.modifiers,
                "pp": s.pp,
                "pp_acc": s.pp_acc,
                "pp_tech": s.pp_tech,
                "pp_speed": s.pp_speed,
                "leaderboard_rank": s.leaderboard_rank,
                "time_set": s.time_set.isoformat() if s.time_set else None,
            }
            for s, d, m in rows
        ],
    }
