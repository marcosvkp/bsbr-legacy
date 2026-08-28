"""GET /maps e /maps/{hash} — catálogo rankeado com decomposição de stars."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache
from app.core.db import get_db
from app.models import Difficulty, Map, MapStatus, Player, RatingHistory, Score

router = APIRouter()

_DIFF_ORDER = {"ExpertPlus": 4, "Expert": 3, "Hard": 2, "Normal": 1, "Easy": 0}


def _map_summary(m: Map) -> dict:
    diffs = sorted(
        (d for d in m.difficulties if d.characteristic == "Standard" and d.total_stars is not None),
        key=lambda d: d.total_stars or 0,
        reverse=True,
    )
    return {
        "hash": m.hash,
        "beatsaver_id": m.beatsaver_id,
        "name": m.name,
        "song_author": m.song_author,
        "mapper": m.mapper,
        "bpm": m.bpm,
        "cover_url": m.cover_url,
        "tags": m.tags,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "difficulties": [
            {
                "name": d.name,
                "total_stars": d.total_stars,
                "acc_stars": d.acc_stars,
                "tech_stars": d.tech_stars,
                "speed_stars": d.speed_stars,
                "style_tags": d.style_tags,
                "max_pp": round((d.total_stars or 0.0) * 42.117208413, 2),
            }
            for d in diffs
        ],
    }


@router.get("/maps")
async def list_maps(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    sort: str = Query("stars", pattern="^(stars|recent|name)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"maps:{sort}:{page}:{page_size}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    total = (
        await db.execute(
            select(func.count()).select_from(Map).where(Map.status == MapStatus.RANKED)
        )
    ).scalar_one()

    order = {
        # Ordena por melhor dificuldade: subquery do max(total_stars)
        "stars": select(func.max(Difficulty.total_stars)).where(Difficulty.map_id == Map.id).scalar_subquery().desc(),
        "recent": Map.created_at.desc(),
        "name": Map.name.asc(),
    }[sort]

    rows = (
        (
            await db.execute(
                select(Map)
                .where(Map.status == MapStatus.RANKED)
                .options(selectinload(Map.difficulties))
                .order_by(order)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    payload = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [_map_summary(m) for m in rows],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload


@router.get("/maps/{map_hash}")
async def get_map(map_hash: str, db: AsyncSession = Depends(get_db)) -> dict:
    cache_key = f"map:{map_hash}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    m = (
        await db.scalars(
            select(Map).where(Map.hash == map_hash).options(selectinload(Map.difficulties))
        )
    ).first()
    if m is None:
        raise HTTPException(status_code=404, detail="mapa não encontrado")

    difficulties = [d for d in m.difficulties if d.characteristic == "Standard"]
    difficulty_ids = [d.id for d in difficulties] or [0]

    top_scores = (
        (
            await db.execute(
                select(Score, Player.name, Difficulty.name, Player.ss_id, Player.avatar_url)
                .join(Player, Score.player_id == Player.id)
                .join(Difficulty, Score.difficulty_id == Difficulty.id)
                .where(Difficulty.map_id == m.id)
                .order_by(Score.pp.desc().nulls_last())
                .limit(50)
            )
        )
        .all()
    )

    history = (
        (
            await db.scalars(
                select(RatingHistory)
                .where(RatingHistory.difficulty_id.in_(difficulty_ids))
                .order_by(RatingHistory.applied_at.desc())
                .limit(10)
            )
        )
        .all()
    )

    diff_names = {d.id: d.name for d in difficulties}

    payload = {
        **_map_summary(m),
        "difficulties_detail": [
            {
                "name": d.name,
                "njs": d.njs,
                "max_score": d.max_score,
                "total_stars": d.total_stars,
                "acc_stars": d.acc_stars,
                "tech_stars": d.tech_stars,
                "speed_stars": d.speed_stars,
                "style_tags": d.style_tags,
                "ranked_at": d.ranked_at.isoformat() if d.ranked_at else None,
            }
            for d in sorted(difficulties, key=lambda x: (_DIFF_ORDER.get(x.name, 99), x.name))
        ],
        "leaderboard": [
            {
                "player_name": name,
                "player_ss_id": ss_id,
                "avatar_url": avatar_url,
                "difficulty": diff_name,
                "score": s.score,
                "acc": s.acc,
                "full_combo": s.full_combo,
                "pp": round(s.pp or 0.0, 2),
                "pp_acc": round(s.pp_acc or 0.0, 2),
                "pp_tech": round(s.pp_tech or 0.0, 2),
                "pp_speed": round(s.pp_speed or 0.0, 2),
                "leaderboard_rank": s.leaderboard_rank,
            }
            for s, name, diff_name, ss_id, avatar_url in top_scores
        ],
        "rating_history": [
            {
                "difficulty_id": h.difficulty_id,
                "difficulty_name": diff_names.get(h.difficulty_id),
                "total_before": h.total_stars_before,
                "total_after": h.total_stars_after,
                "acc_before": h.acc_stars_before,
                "acc_after": h.acc_stars_after,
                "tech_before": h.tech_stars_before,
                "tech_after": h.tech_stars_after,
                "speed_before": h.speed_stars_before,
                "speed_after": h.speed_stars_after,
                "reason": h.reason,
                "applied_by": h.applied_by,
                "applied_at": h.applied_at.isoformat() if h.applied_at else None,
            }
            for h in history
        ],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload
